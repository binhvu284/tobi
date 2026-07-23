// News V2 shared card renderer (#23, N10) — used by both Feed and Favorites
// (plan §8: "Favorites reuses the renderer", "Do not place cards inside cards").
// Every mutation goes through the N06 contract: Idempotency-Key + optimistic
// version (stale → 409 with the server's detail surfaced honestly). Dislike shows
// the inline 10-second Undo state; open/dwell events are fire-and-forget and
// bounded (dwell sent once per item, only when ≥5 s visible, capped at 30 min).
import { useEffect, useRef, useState } from 'react'
import {
  ExternalLink, EyeOff, Loader2, Sparkles, Star, StickyNote, ThumbsDown, ThumbsUp, Undo2,
} from 'lucide-react'
import {
  patchNewsV2Interaction, postNewsV2Event, putNewsV2Note,
  type NewsV2Interaction, type NewsV2ItemEntry,
} from '../../api'
import { useToast } from '../../context/ToastProvider'
import SourceLogo from '../SourceLogo'

export function ago(iso: string | null | undefined): string {
  if (!iso) return '—'
  const ms = Date.now() - new Date(iso).getTime()
  if (!Number.isFinite(ms)) return '—'
  const m = Math.floor(ms / 60_000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 48) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

export const DEFAULT_INTERACTION: NewsV2Interaction = {
  reaction: 'none', favorite: 0, note: null, opens: 0, dwell_ms: 0, version: 0,
}

/** Per-item state the parent list owns so virtualized unmount/remount keeps it. */
export type CardOverride = { interaction: NewsV2Interaction; undoUntil?: number; committed?: boolean }

// Dwell events are sent at most once per item per page load (bounded batch).
const dwellSent = new Set<number>()
const DWELL_MIN_MS = 5000
const DWELL_MAX_MS = 1_800_000

export default function NewsCard({ entry, override, showReasons, onChange, onRemoved }: {
  entry: NewsV2ItemEntry
  override?: CardOverride
  /** Render the deterministic "Why shown" reasons (For You mode only). */
  showReasons?: boolean
  onChange: (itemId: number, next: CardOverride) => void
  /** Favorites view: called after a successful unfavorite so the row leaves the list. */
  onRemoved?: (itemId: number) => void
}) {
  const { toast } = useToast()
  const ix = override?.interaction ?? entry.interaction ?? DEFAULT_INTERACTION
  const undoUntil = override?.undoUntil
  const committed = override?.committed
    ?? (ix.reaction === 'dislike' && !undoUntil)          // server-known dislike, window unknown
  const [busy, setBusy] = useState<string | null>(null)
  const [, setTick] = useState(0)
  const [noteOpen, setNoteOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const [reasonsOpen, setReasonsOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement | null>(null)

  // ── bounded dwell tracking: ≥50% visible for ≥5 s, sent once per item ──────────
  useEffect(() => {
    const node = rootRef.current
    if (!node || dwellSent.has(entry.item_id)) return
    let since: number | null = null
    const flush = () => {
      if (since === null) return
      const ms = Math.min(DWELL_MAX_MS, Math.round(performance.now() - since))
      since = null
      if (ms >= DWELL_MIN_MS && !dwellSent.has(entry.item_id)) {
        dwellSent.add(entry.item_id)
        void postNewsV2Event(entry.item_id, { type: 'dwell', ms }).catch(() => {})
      }
    }
    const io = new IntersectionObserver(hits => {
      for (const hit of hits) {
        if (hit.isIntersecting) since = since ?? performance.now()
        else flush()
      }
    }, { threshold: 0.5 })
    io.observe(node)
    return () => { flush(); io.disconnect() }
  }, [entry.item_id])

  // ── inline 10-second undo countdown (server window is authoritative) ───────────
  useEffect(() => {
    if (!undoUntil) return
    const timer = window.setInterval(() => {
      if (Date.now() >= undoUntil) {
        window.clearInterval(timer)
        onChange(entry.item_id, { interaction: ix, committed: true })
      } else setTick(k => k + 1)
    }, 250)
    return () => window.clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [undoUntil, entry.item_id])

  const mutate = async (action: 'like' | 'dislike' | 'undo' | 'favorite' | 'unfavorite') => {
    if (busy) return
    setBusy(action)
    try {
      const state = await patchNewsV2Interaction(entry.item_id, action, ix.version)
      const next: CardOverride = { interaction: state }
      if (action === 'dislike') next.undoUntil = Date.now() + 10_000
      onChange(entry.item_id, next)
      if (action === 'unfavorite') onRemoved?.(entry.item_id)
    } catch (err) {
      // 409 carries the server's honest detail (stale version / undo window expired)
      toast({ kind: 'error', title: 'Action failed', detail: err instanceof Error ? err.message : String(err) })
    } finally { setBusy(null) }
  }

  const saveNote = async (clear: boolean) => {
    if (busy) return
    setBusy('note')
    try {
      const text = clear ? null : (draft.trim() || null)
      const state = await putNewsV2Note(entry.item_id, text, ix.version)
      onChange(entry.item_id, { interaction: state, undoUntil, committed })
      setNoteOpen(false)
      toast({ kind: 'success', title: text ? 'Note saved' : 'Note cleared' })
    } catch (err) {
      toast({ kind: 'error', title: 'Note not saved', detail: err instanceof Error ? err.message : String(err) })
    } finally { setBusy(null) }
  }

  const recordOpen = () => {
    void postNewsV2Event(entry.item_id, { type: 'open' })
      .then(state => onChange(entry.item_id, { interaction: state, undoUntil, committed }))
      .catch(() => {})
  }

  // ── committed dislike: collapsed row (item leaves the feed on next snapshot) ───
  if (committed && ix.reaction === 'dislike') {
    return (
      <div ref={rootRef} className="flex items-center gap-2 rounded-lg border border-border bg-surface/30 px-4 py-2.5">
        <EyeOff size={13} className="shrink-0 text-muted" />
        <span className="min-w-0 flex-1 truncate text-xs text-muted">Disliked — hidden from your feed on the next refresh.</span>
        <button onClick={() => void mutate('undo')} disabled={busy !== null}
          className="inline-flex shrink-0 items-center gap-1 text-[11px] text-muted hover:text-accent disabled:opacity-50">
          {busy === 'undo' ? <Loader2 size={11} className="animate-spin" /> : <Undo2 size={11} />} Undo
        </button>
      </div>
    )
  }

  const undoRemaining = undoUntil ? Math.max(0, Math.ceil((undoUntil - Date.now()) / 1000)) : 0
  const timeLabel = ago(entry.published_at ?? entry.first_seen_at)

  return (
    <article ref={rootRef} className="overflow-hidden rounded-lg border border-border bg-surface/40">
      <div className="p-4">
        <header className="flex items-center gap-2 text-[11px] text-muted">
          <SourceLogo name={entry.source} size={12} variant="inline" />
          <span className="font-medium text-text/80">{entry.source}</span>
          {entry.item_type && entry.item_type !== 'article' && (
            <span className="rounded-full border border-border px-1.5 py-px text-[10px] uppercase tracking-wide">{entry.item_type}</span>
          )}
          <span>· {timeLabel}</span>
          {typeof entry.engagement === 'number' && entry.engagement > 0 && <span>· ▲ {entry.engagement}</span>}
          {(ix.favorite === 1 || (ix.note ?? '').trim()) && (
            <span title="Favorites and notes are exempt from retention" className="ml-auto shrink-0 text-[10px] text-accent/80">never expires</span>
          )}
        </header>

        {entry.media_key && (
          <div className="mt-3 overflow-hidden rounded-md border border-border/60 bg-background/50">
            {/* reserved aspect space → no layout shift; served only from the validated cache */}
            <img src={`/api/explore/v2/media/${entry.media_key}`} alt="" loading="lazy"
              className="aspect-video w-full object-cover"
              onError={event => { (event.currentTarget.parentElement as HTMLElement).style.display = 'none' }} />
          </div>
        )}

        <h3 className="mt-2.5 text-sm font-semibold leading-5 text-text">
          <a href={entry.url} target="_blank" rel="noreferrer" onClick={recordOpen} className="hover:text-accent">{entry.title}</a>
        </h3>
        {entry.excerpt && <p className="mt-1.5 line-clamp-3 text-xs leading-5 text-muted">{entry.excerpt}</p>}

        {showReasons && (entry.reasons?.length ?? 0) > 0 && reasonsOpen && (
          <ul className="mt-2.5 space-y-1 rounded-md border border-accent/20 bg-accent/[0.04] px-3 py-2">
            {entry.reasons!.map(reason => (
              <li key={reason.reason} className="flex items-center gap-1.5 text-[11px] text-text/85">
                <Sparkles size={10} className="shrink-0 text-accent" /> {reason.reason}
              </li>
            ))}
          </ul>
        )}

        {undoUntil && ix.reaction === 'dislike' ? (
          <div className="mt-3 flex items-center gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-2">
            <EyeOff size={13} className="shrink-0 text-warning" />
            <span className="min-w-0 flex-1 text-xs text-text">Hidden from your feed.</span>
            <button onClick={() => void mutate('undo')} disabled={busy !== null}
              className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md border border-border bg-background px-2.5 text-xs font-medium text-text hover:border-accent/50 disabled:opacity-50">
              {busy === 'undo' ? <Loader2 size={12} className="animate-spin" /> : <Undo2 size={12} />} Undo ({undoRemaining}s)
            </button>
          </div>
        ) : (
          <footer className="mt-3 flex flex-wrap items-center gap-1.5">
            <ActionButton label="Like" active={ix.reaction === 'like'} busy={busy === 'like'}
              onClick={() => void mutate('like')} icon={<ThumbsUp size={13} />} />
            <ActionButton label="Dislike" active={false} busy={busy === 'dislike'}
              onClick={() => void mutate('dislike')} icon={<ThumbsDown size={13} />} />
            <ActionButton label={ix.favorite === 1 ? 'Saved' : 'Favorite'} active={ix.favorite === 1}
              busy={busy === 'favorite' || busy === 'unfavorite'}
              onClick={() => void mutate(ix.favorite === 1 ? 'unfavorite' : 'favorite')}
              icon={<Star size={13} className={ix.favorite === 1 ? 'fill-current' : ''} />} />
            <ActionButton label={(ix.note ?? '').trim() ? 'Note ·' : 'Note'} active={Boolean((ix.note ?? '').trim())}
              busy={false}
              onClick={() => { setDraft(ix.note ?? ''); setNoteOpen(open => !open) }}
              icon={<StickyNote size={13} />} />
            {showReasons && (entry.reasons?.length ?? 0) > 0 && (
              <ActionButton label="Why shown" active={reasonsOpen} busy={false}
                onClick={() => setReasonsOpen(open => !open)} icon={<Sparkles size={13} />} />
            )}
            <a href={entry.url} target="_blank" rel="noreferrer" onClick={recordOpen}
              className="ml-auto inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-[11px] text-muted hover:text-accent">
              <ExternalLink size={12} /> Open
            </a>
          </footer>
        )}

        {noteOpen && (
          <div className="mt-3 rounded-md border border-border bg-background/60 p-2.5">
            <textarea value={draft} onChange={event => setDraft(event.target.value)} rows={3}
              placeholder="Private note — only you see this. Noted items never expire."
              className="w-full resize-y rounded-md border border-border bg-background px-2.5 py-2 text-xs text-text outline-none focus:border-accent" />
            <div className="mt-2 flex items-center justify-end gap-2">
              {(ix.note ?? '').trim() && (
                <button onClick={() => void saveNote(true)} disabled={busy !== null}
                  className="inline-flex h-7 items-center rounded-md px-2.5 text-[11px] text-muted hover:text-danger disabled:opacity-50">Clear note</button>
              )}
              <button onClick={() => setNoteOpen(false)} disabled={busy !== null}
                className="inline-flex h-7 items-center rounded-md border border-border px-2.5 text-[11px] text-text disabled:opacity-50">Cancel</button>
              <button onClick={() => void saveNote(false)} disabled={busy !== null}
                className="inline-flex h-7 items-center gap-1.5 rounded-md bg-accent px-3 text-[11px] font-semibold text-background disabled:opacity-50">
                {busy === 'note' ? <Loader2 size={11} className="animate-spin" /> : null} Save
              </button>
            </div>
          </div>
        )}
      </div>
    </article>
  )
}

function ActionButton({ label, icon, active, busy, onClick }: {
  label: string; icon: React.ReactNode; active: boolean; busy: boolean; onClick: () => void
}) {
  return (
    <button onClick={onClick} disabled={busy}
      className={`inline-flex h-7 items-center gap-1.5 rounded-md border px-2.5 text-[11px] font-medium transition-colors disabled:opacity-50 ${
        active ? 'border-accent/50 bg-accent/10 text-accent' : 'border-border text-muted hover:border-accent/30 hover:text-text'}`}>
      {busy ? <Loader2 size={12} className="animate-spin" /> : icon} {label}
    </button>
  )
}

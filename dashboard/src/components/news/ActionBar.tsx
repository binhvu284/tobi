// Shared interaction bar (#23, owner: "add action buttons — like, dislike, note,
// favourite — everywhere"). One reusable, optimistic control used by the GitHub table,
// Source Explore, and Latest Releases so feedback is consistent and immediately drives
// the personalization + content-creator algorithms. onChange lets a parent react to a
// favourite (e.g. "keep on refresh, otherwise disposable").
import { useState } from 'react'
import { Brain, Loader2, StickyNote, ThumbsDown, ThumbsUp, Star } from 'lucide-react'
import { patchNewsV2Interaction, postNewsV2SaveToBrain, putNewsV2Note, type NewsV2Interaction } from '../../api.explore'
import { useToast } from '../../context/ToastProvider'
import { DEFAULT_INTERACTION } from './NewsCard'

type Action = 'like' | 'dislike' | 'favorite' | 'note' | 'brain'

export default function ActionBar({ itemId, interaction, onChange, size = 'sm', actions, savedToBrain }: {
  itemId: number
  interaction?: NewsV2Interaction
  onChange?: (next: NewsV2Interaction) => void
  size?: 'sm' | 'xs'
  actions?: Action[]
  /** N11: whether this story is already a Brain memory (the feed sends it with the page). */
  savedToBrain?: boolean
}) {
  const show = (a: Action) => !actions || actions.includes(a)
  const { toast } = useToast()
  const [ix, setIx] = useState<NewsV2Interaction>(interaction ?? DEFAULT_INTERACTION)
  const [busy, setBusy] = useState<string | null>(null)
  const [noteOpen, setNoteOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const [inBrain, setInBrain] = useState(Boolean(savedToBrain))

  const apply = (next: NewsV2Interaction) => { setIx(next); onChange?.(next) }

  const mutate = async (action: 'like' | 'dislike' | 'undo' | 'favorite' | 'unfavorite', label: string) => {
    if (busy) return
    setBusy(label)
    try { apply(await patchNewsV2Interaction(itemId, action, ix.version)) }
    catch (err) { toast({ kind: 'error', title: 'Action failed', detail: err instanceof Error ? err.message : String(err) }) }
    finally { setBusy(null) }
  }

  const saveNote = async (clear: boolean) => {
    if (busy) return
    setBusy('note')
    try {
      const text = clear ? null : (draft.trim() || null)
      apply(await putNewsV2Note(itemId, text, ix.version))
      setNoteOpen(false)
      toast({ kind: 'success', title: text ? 'Note saved' : 'Note cleared' })
    } catch (err) { toast({ kind: 'error', title: 'Note not saved', detail: err instanceof Error ? err.message : String(err) }) }
    finally { setBusy(null) }
  }

  // N11: the ONLY News→Brain write. Explicit press, once per story — a second press is a
  // no-op server-side, so the button becomes a state, not a repeatable action.
  const saveToBrain = async () => {
    if (busy || inBrain) return
    setBusy('brain')
    try {
      const res = await postNewsV2SaveToBrain(itemId)
      setInBrain(true)
      toast({ kind: 'success', title: res.already_saved ? 'Already in Brain' : 'Saved to Brain',
        detail: res.already_saved ? 'TOBI remembered this story earlier.' : 'TOBI will remember this story.' })
    } catch (err) {
      toast({ kind: 'error', title: 'Not saved to Brain', detail: err instanceof Error ? err.message : String(err) })
    } finally { setBusy(null) }
  }

  const iconSize = size === 'xs' ? 12 : 13
  const btn = `inline-flex items-center justify-center rounded-md border transition-colors disabled:opacity-50 ${
    size === 'xs' ? 'h-6 w-6' : 'h-7 w-7'}`
  const on = 'border-accent/50 bg-accent/10 text-accent'
  const off = 'border-border text-muted hover:border-accent/40 hover:text-text'
  const noted = Boolean((ix.note ?? '').trim())

  return (
    <div onClick={event => event.preventDefault()} className="relative">
      <div className="flex items-center gap-1">
        {show('like') && (
          <button title="Like" aria-label="Like" disabled={busy !== null} onClick={() => mutate('like', 'like')}
            className={`${btn} ${ix.reaction === 'like' ? on : off}`}>
            {busy === 'like' ? <Loader2 size={iconSize} className="animate-spin" /> : <ThumbsUp size={iconSize} className={ix.reaction === 'like' ? 'fill-current' : ''} />}
          </button>
        )}
        {show('dislike') && (
          <button title="Dislike" aria-label="Dislike" disabled={busy !== null} onClick={() => mutate('dislike', 'dislike')}
            className={`${btn} ${ix.reaction === 'dislike' ? 'border-danger/50 bg-danger/10 text-danger' : off}`}>
            {busy === 'dislike' ? <Loader2 size={iconSize} className="animate-spin" /> : <ThumbsDown size={iconSize} />}
          </button>
        )}
        {show('favorite') && (
          <button title={ix.favorite === 1 ? 'Saved — keeps on refresh' : 'Favorite'} aria-label="Favorite" disabled={busy !== null}
            onClick={() => mutate(ix.favorite === 1 ? 'unfavorite' : 'favorite', 'fav')}
            className={`${btn} ${ix.favorite === 1 ? 'border-amber-400/50 bg-amber-400/10 text-amber-400' : off}`}>
            {busy === 'fav' ? <Loader2 size={iconSize} className="animate-spin" /> : <Star size={iconSize} className={ix.favorite === 1 ? 'fill-current' : ''} />}
          </button>
        )}
        {show('brain') && (
          <button title={inBrain ? 'TOBI remembers this story' : 'Save to Brain — TOBI remembers this story'}
            aria-label="Save to Brain" disabled={busy !== null || inBrain}
            onClick={saveToBrain}
            className={`${btn} ${inBrain ? 'border-violet-400/50 bg-violet-400/10 text-violet-400' : off}`}>
            {busy === 'brain' ? <Loader2 size={iconSize} className="animate-spin" /> : <Brain size={iconSize} className={inBrain ? 'fill-current' : ''} />}
          </button>
        )}
        {show('note') && (
          <button title={noted ? 'Edit note' : 'Add note'} aria-label="Note" disabled={busy !== null}
            onClick={() => { setDraft(ix.note ?? ''); setNoteOpen(open => !open) }}
            className={`${btn} ${noted ? on : off}`}>
            <StickyNote size={iconSize} />
          </button>
        )}
      </div>
      {noteOpen && (
        <div onClick={event => event.stopPropagation()}
          className="absolute right-0 top-9 z-20 w-64 rounded-md border border-border bg-surface p-2.5 shadow-xl">
          <textarea autoFocus value={draft} onChange={event => setDraft(event.target.value)} rows={3}
            placeholder="Private note" className="w-full resize-y rounded-md border border-border bg-background px-2.5 py-2 text-xs text-text outline-none focus:border-accent" />
          <div className="mt-2 flex items-center justify-end gap-2">
            {noted && <button onClick={() => saveNote(true)} disabled={busy !== null} className="inline-flex h-7 items-center rounded-md px-2.5 text-[11px] text-muted hover:text-danger disabled:opacity-50">Clear</button>}
            <button onClick={() => setNoteOpen(false)} disabled={busy !== null} className="inline-flex h-7 items-center rounded-md border border-border px-2.5 text-[11px] text-text disabled:opacity-50">Cancel</button>
            <button onClick={() => saveNote(false)} disabled={busy !== null} className="inline-flex h-7 items-center gap-1.5 rounded-md bg-accent px-3 text-[11px] font-semibold text-background disabled:opacity-50">
              {busy === 'note' ? <Loader2 size={11} className="animate-spin" /> : null} Save
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

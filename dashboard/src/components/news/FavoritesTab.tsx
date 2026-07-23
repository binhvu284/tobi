// News V2 Favorites tab (#23, N10) — the durable saved-items view (plan §8).
// Reuses the shared NewsCard renderer; NEVER auto-refreshes (no reloadKey, no
// snapshot dependency — it reads the keyset-cursored favorites list directly) and
// favorites/notes never expire (retention-exempt server-side). Source and
// note-only filters are server-side; the search box and type filter narrow the
// loaded rows client-side and say so.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Loader2, RefreshCw, Search, Star } from 'lucide-react'
import { getNewsV2Feed, type NewsV2ItemEntry } from '../../api'
import NewsCard, { type CardOverride } from './NewsCard'

export default function FavoritesTab() {
  const [entries, setEntries] = useState<NewsV2ItemEntry[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [overrides, setOverrides] = useState<Record<number, CardOverride>>({})
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [q, setQ] = useState('')
  const [source, setSource] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [notesOnly, setNotesOnly] = useState(false)

  const load = useCallback(async (reset: boolean, cur?: string | null) => {
    if (reset) setLoading(true)
    else setLoadingMore(true)
    try {
      const page = await getNewsV2Feed({
        mode: 'favorites', source: source || undefined, has_note: notesOnly || undefined,
        cursor: reset ? undefined : cur ?? undefined, limit: 40,
      })
      setEntries(current => reset ? page.entries : (() => {
        const known = new Set(current.map(entry => entry.item_id))
        return [...current, ...page.entries.filter(entry => !known.has(entry.item_id))]
      })())
      setCursor(page.next_cursor)
      if (reset) setOverrides({})
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      if (reset) setLoading(false)
      else setLoadingMore(false)
    }
  }, [source, notesOnly])
  useEffect(() => { void load(true) }, [load])

  const onCardChange = useCallback((itemId: number, next: CardOverride) => {
    setOverrides(current => ({ ...current, [itemId]: next }))
  }, [])
  const onRemoved = useCallback((itemId: number) => {
    setEntries(current => current.filter(entry => entry.item_id !== itemId))
  }, [])

  // Distinct sources/types come from what is actually saved — never invented.
  const knownSources = useMemo(() => [...new Set(entries.map(entry => entry.source))].sort(), [entries])
  const knownTypes = useMemo(() => [...new Set(entries.map(entry => entry.item_type).filter(Boolean))].sort() as string[], [entries])

  const view = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return entries.filter(entry => {
      const ix = overrides[entry.item_id]?.interaction ?? entry.interaction
      if (typeFilter && entry.item_type !== typeFilter) return false
      if (!needle) return true
      return entry.title.toLowerCase().includes(needle)
        || (ix?.note ?? '').toLowerCase().includes(needle)
        || (entry.excerpt ?? '').toLowerCase().includes(needle)
    })
  }, [entries, overrides, q, typeFilter])

  return (
    <div className="mx-auto max-w-3xl space-y-3">
      <section className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-surface/40 px-3 py-2.5">
        <div className="relative min-w-[180px] flex-1">
          <Search size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
          <input value={q} onChange={event => setQ(event.target.value)}
            placeholder="Search saved titles & notes (loaded items)"
            className="h-8 w-full rounded-md border border-border bg-background pl-8 pr-3 text-xs text-text outline-none focus:border-accent" />
        </div>
        <select value={source} onChange={event => setSource(event.target.value)}
          className="h-8 rounded-md border border-border bg-background px-2 text-[11px] text-text outline-none focus:border-accent">
          <option value="">All sources</option>
          {knownSources.map(name => <option key={name} value={name}>{name}</option>)}
        </select>
        {knownTypes.length > 1 && (
          <select value={typeFilter} onChange={event => setTypeFilter(event.target.value)}
            className="h-8 rounded-md border border-border bg-background px-2 text-[11px] text-text outline-none focus:border-accent">
            <option value="">All types</option>
            {knownTypes.map(name => <option key={name} value={name}>{name}</option>)}
          </select>
        )}
        <button onClick={() => setNotesOnly(current => !current)}
          className={`inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-[11px] font-medium ${notesOnly ? 'border-accent bg-accent/10 text-accent' : 'border-border text-muted hover:text-text'}`}>
          With notes
        </button>
      </section>

      {loading ? (
        <div className="space-y-3">{[0, 1].map(i => (
          <div key={i} className="h-36 animate-pulse rounded-lg border border-border bg-surface/40" />))}
        </div>
      ) : error ? (
        <section className="rounded-lg border border-danger/40 bg-danger/5 px-5 py-6 text-center">
          <AlertTriangle size={18} className="mx-auto text-danger" />
          <p className="mt-2 text-sm text-text">Favorites are unavailable.</p>
          <p className="mt-1 text-xs text-muted">{error}</p>
          <button onClick={() => void load(true)} className="mt-4 inline-flex h-8 items-center gap-2 rounded-md border border-border px-3 text-xs text-text hover:bg-overlay/5"><RefreshCw size={13} /> Retry</button>
        </section>
      ) : view.length === 0 ? (
        <section className="rounded-lg border border-dashed border-border bg-surface/30 px-6 py-12 text-center">
          <Star size={18} className="mx-auto text-muted" />
          <p className="mt-3 text-sm text-text">{entries.length === 0 ? 'Nothing saved yet.' : 'No favorites match these filters.'}</p>
          <p className="mt-1 text-xs text-muted">
            {entries.length === 0 ? 'Tap the star on any feed card — favorites and their notes never expire.' : 'Clear the search or filters to see everything saved.'}
          </p>
        </section>
      ) : (
        <>
          <div className="space-y-3">
            {view.map(entry => (
              <NewsCard key={entry.item_id} entry={entry} override={overrides[entry.item_id]}
                onChange={onCardChange} onRemoved={onRemoved} />
            ))}
          </div>
          <div className="flex justify-center py-2">
            {loadingMore ? (
              <span className="inline-flex items-center gap-2 text-xs text-muted"><Loader2 size={13} className="animate-spin" /> Loading more…</span>
            ) : cursor ? (
              <button onClick={() => void load(false, cursor)} className="inline-flex h-8 items-center rounded-md border border-border px-4 text-xs text-text hover:border-accent/40">Load more</button>
            ) : null}
          </div>
        </>
      )}
    </div>
  )
}

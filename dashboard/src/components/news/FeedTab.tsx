// News V2 Feed tab (#23, N10) — virtualized personalized feed (plan §8/§9).
// @tanstack/react-virtual windows the list against the workspace's own scroll
// container (≤~60 DOM items regardless of feed length); pages come from immutable
// rank snapshots via pinned cursors, so scrolling never shifts under the reader.
// A completed refresh NEVER jumps the feed: the new snapshot is probed in the
// background and swapped in only after the owner activates the "N new posts"
// banner. Interaction state lives up here so virtualized unmount/remount of cards
// (and the 10-second dislike undo window) survives scrolling.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { softFail } from '../../lib/report'
import { createPortal } from 'react-dom'
import { useVirtualizer } from '@tanstack/react-virtual'
import {
  AlertTriangle, ArrowUp, Brain, Loader2, RefreshCw, Rss, SlidersHorizontal, Sparkles, X,
} from 'lucide-react'
import { ActionButton } from '../async-ui'
import { getNewsV2Feed, getNewsV2Profile, getNewsV2TrendingSources, type NewsV2ItemEntry } from '../../api.explore'
import SourceLogo from '../SourceLogo'
import NewsCard, { type CardOverride } from './NewsCard'

type FeedMode = 'for_you' | 'latest'
type Profile = Awaited<ReturnType<typeof getNewsV2Profile>>
const PAGE = 25

export default function FeedTab({ reloadKey }: { reloadKey: number }) {
  const [mode, setMode] = useState<FeedMode>('for_you')
  const [source, setSource] = useState('')
  const [entries, setEntries] = useState<NewsV2ItemEntry[]>([])
  const [snapshotId, setSnapshotId] = useState<number | null>(null)
  const [cursor, setCursor] = useState<string | null>(null)
  const [overrides, setOverrides] = useState<Record<number, CardOverride>>({})
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState<{ entries: NewsV2ItemEntry[]; snapshot_id: number | null; next_cursor: string | null; count: number } | null>(null)
  const [sources, setSources] = useState<{ source: string; items: number }[]>([])
  const [profile, setProfile] = useState<Profile | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)

  const load = useCallback(async (nextMode: FeedMode, nextSource: string) => {
    setLoading(true)
    setPending(null)
    try {
      const page = await getNewsV2Feed({ mode: nextMode, source: nextSource || undefined, limit: PAGE })
      setEntries(page.entries)
      setSnapshotId(page.snapshot_id ?? null)
      setCursor(page.next_cursor)
      setOverrides({})
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally { setLoading(false) }
  }, [])
  useEffect(() => { void load(mode, source) }, [load, mode, source])

  // Rail data: sources are canonical-store facts; the profile is the transparent
  // "what TOBI learned" view — both best-effort, the feed renders without them.
  useEffect(() => {
    void getNewsV2TrendingSources().then(res => setSources(res.sources)).catch(softFail('your feed'))
    void getNewsV2Profile().then(setProfile).catch(softFail('your feed'))
  }, [reloadKey])

  // ── refresh completed → probe the new snapshot WITHOUT touching the list ───────
  const firstReload = useRef(true)
  useEffect(() => {
    if (firstReload.current) { firstReload.current = false; return }
    void (async () => {
      try {
        const fresh = await getNewsV2Feed({ mode, source: source || undefined, limit: PAGE })
        if ((fresh.snapshot_id ?? null) === snapshotId) return
        const known = new Set(entries.map(entry => entry.item_id))
        const count = fresh.entries.filter(entry => !known.has(entry.item_id)).length
        if (count > 0) setPending({ ...fresh, snapshot_id: fresh.snapshot_id ?? null, count })
      } catch { /* probe only — the visible feed stays untouched */ }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reloadKey])

  const loadMore = useCallback(async () => {
    if (!cursor || loadingMore) return
    setLoadingMore(true)
    try {
      const page = await getNewsV2Feed({ mode, source: source || undefined, cursor, limit: PAGE })
      setEntries(current => {
        const known = new Set(current.map(entry => entry.item_id))
        return [...current, ...page.entries.filter(entry => !known.has(entry.item_id))]
      })
      setCursor(page.next_cursor)
    } catch { /* keep the Load-more affordance; the next scroll retries */ }
    finally { setLoadingMore(false) }
  }, [cursor, loadingMore, mode, source])

  // ── virtualization against the workspace scroll container (plan §9) ────────────
  // The tab shell scrolls in its own `absolute inset-0 overflow-y-auto` wrapper,
  // so walk up to the nearest scrollable ancestor; scrollEl is React state so the
  // virtualizer is guaranteed a rerender once the element is known.
  const listRef = useRef<HTMLDivElement | null>(null)
  const [scrollEl, setScrollEl] = useState<HTMLElement | null>(null)
  const [margin, setMargin] = useState(0)
  useEffect(() => {
    let el: HTMLElement | null = listRef.current?.parentElement ?? null
    while (el && el !== document.body) {
      if (/(auto|scroll)/.test(getComputedStyle(el).overflowY)) break
      el = el.parentElement
    }
    const found = el && el !== document.body ? el : document.documentElement
    if (listRef.current) {
      setMargin(Math.max(0, Math.round(
        listRef.current.getBoundingClientRect().top
        - found.getBoundingClientRect().top + found.scrollTop)))
    }
    setScrollEl(found)
  }, [loading])

  const virtualizer = useVirtualizer({
    count: entries.length,
    getScrollElement: () => scrollEl,
    estimateSize: () => 190,
    overscan: 6,
    scrollMargin: margin,
    getItemKey: index => entries[index].item_id,
  })
  const virtualItems = virtualizer.getVirtualItems()

  // Infinite scroll: fetch the next pinned-cursor page as the window nears the end.
  useEffect(() => {
    const last = virtualItems[virtualItems.length - 1]
    if (last && last.index >= entries.length - 5 && cursor && !loadingMore && !loading) void loadMore()
  }, [virtualItems, entries.length, cursor, loadingMore, loading, loadMore])

  const showPending = () => {
    if (!pending) return
    setEntries(pending.entries)
    setSnapshotId(pending.snapshot_id)
    setCursor(pending.next_cursor)
    setOverrides({})
    setPending(null)
    scrollEl?.scrollTo({ top: Math.max(0, margin - 130), behavior: 'smooth' })
  }

  const onCardChange = useCallback((itemId: number, next: CardOverride) => {
    setOverrides(current => ({ ...current, [itemId]: next }))
  }, [])

  const rail = (
    <RailContent mode={mode} setMode={setMode} source={source} setSource={setSource}
      sources={sources} profile={profile} />
  )

  return (
    <div className="relative mx-auto flex max-w-6xl items-start gap-5">
      <div className="relative min-w-0 flex-1">
        {/* mobile: mode control inline, the rest of the rail lives in the drawer */}
        <div className="mb-3 flex items-center gap-2 lg:hidden">
          <ModeControl mode={mode} setMode={setMode} />
          <button onClick={() => setDrawerOpen(true)}
            className="ml-auto inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-2.5 text-[11px] text-text hover:border-accent/40">
            <SlidersHorizontal size={12} /> Filters{source ? ` · ${source}` : ''}
          </button>
        </div>

        {/* "N new posts" — floating, never reflows or jumps the list (plan §8) */}
        {pending && (
          <div className="pointer-events-none sticky top-28 z-10 flex justify-center">
            <button onClick={showPending}
              className="pointer-events-auto inline-flex h-8 -translate-y-1 items-center gap-2 rounded-full border border-accent/40 bg-background px-4 text-xs font-semibold text-accent shadow-lg hover:bg-accent/10">
              <ArrowUp size={13} /> {pending.count} new post{pending.count === 1 ? '' : 's'}
            </button>
          </div>
        )}

        {loading ? (
          <div className="space-y-3">{[0, 1, 2].map(i => (
            <div key={i} className="h-40 animate-pulse rounded-lg border border-border bg-surface/40" />))}
          </div>
        ) : error ? (
          <section className="rounded-lg border border-danger/40 bg-danger/5 px-5 py-6 text-center">
            <AlertTriangle size={18} className="mx-auto text-danger" />
            <p className="mt-2 text-sm text-text">The feed is unavailable.</p>
            <p className="mt-1 text-xs text-muted">{error}</p>
            <ActionButton onAction={() => load(mode, source)} icon={<RefreshCw size={13} />} className="mt-4 inline-flex h-8 items-center gap-2 rounded-md border border-border px-3 text-xs text-text hover:bg-overlay/5"> Retry</ActionButton>
          </section>
        ) : entries.length === 0 ? (
          <section className="rounded-lg border border-dashed border-border bg-surface/30 px-6 py-12 text-center">
            <Rss size={18} className="mx-auto text-muted" />
            <p className="mt-3 text-sm text-text">{source ? `No items from ${source} on this page.` : 'No feed snapshot yet.'}</p>
            <p className="mt-1 text-xs text-muted">{source ? 'Try clearing the source filter or loading more.' : 'Run a News Feed refresh to collect and rank posts — nothing here is ever mocked.'}</p>
          </section>
        ) : (
          <>
            <div ref={listRef} className="relative" style={{ height: virtualizer.getTotalSize() }}>
              {virtualItems.map(item => (
                <div key={item.key} data-index={item.index} ref={virtualizer.measureElement}
                  className="absolute left-0 top-0 w-full pb-3"
                  style={{ transform: `translateY(${item.start - margin}px)` }}>
                  <NewsCard entry={entries[item.index]} override={overrides[entries[item.index].item_id]}
                    showReasons={mode === 'for_you'} onChange={onCardChange} />
                </div>
              ))}
            </div>
            <div className="flex justify-center py-3">
              {loadingMore ? (
                <span className="inline-flex items-center gap-2 text-xs text-muted"><Loader2 size={13} className="animate-spin" /> Loading more…</span>
              ) : cursor ? (
                <ActionButton onAction={() => loadMore()} className="inline-flex h-8 items-center gap-2 rounded-md border border-border px-4 text-xs text-text hover:border-accent/40">Load more</ActionButton>
              ) : (
                <span className="text-[11px] text-muted">End of this snapshot.</span>
              )}
            </div>
          </>
        )}
      </div>

      {/* desktop sticky rail (plan §8) */}
      <aside className="hidden w-72 shrink-0 lg:block">
        <div className="sticky top-32 space-y-3">{rail}</div>
      </aside>

      {/* mobile drawer / bottom sheet */}
      {createPortal(
        drawerOpen ? (
          <div className="fixed inset-0 z-50 lg:hidden" onClick={() => setDrawerOpen(false)}>
            <div className="absolute inset-0 bg-background/70 backdrop-blur-sm" />
            <div onClick={event => event.stopPropagation()}
              className="absolute inset-x-0 bottom-0 max-h-[80vh] overflow-y-auto rounded-t-xl border-t border-border bg-surface p-4 shadow-2xl">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-text">Feed controls</h2>
                <button onClick={() => setDrawerOpen(false)} className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted hover:text-text"><X size={16} /></button>
              </div>
              <div className="space-y-3">{rail}</div>
            </div>
          </div>
        ) : null,
        document.body,
      )}
    </div>
  )
}

function ModeControl({ mode, setMode }: { mode: FeedMode; setMode: (m: FeedMode) => void }) {
  return (
    <div className="flex overflow-hidden rounded-md border border-border">
      {(['for_you', 'latest'] as FeedMode[]).map(value => (
        <button key={value} onClick={() => setMode(value)}
          className={`px-3 py-1.5 text-[11px] font-medium transition-colors ${mode === value ? 'bg-accent text-background' : 'text-muted hover:text-text'}`}>
          {value === 'for_you' ? 'For You' : 'Latest'}
        </button>
      ))}
    </div>
  )
}

function RailContent({ mode, setMode, source, setSource, sources, profile }: {
  mode: FeedMode; setMode: (m: FeedMode) => void
  source: string; setSource: (s: string) => void
  sources: { source: string; items: number }[]
  profile: Profile | null
}) {
  const topTopics = useMemo(() => Object.entries(profile?.topics ?? {})
    .sort((a, b) => b[1] - a[1]).slice(0, 5), [profile])
  const topSources = useMemo(() => Object.entries(profile?.sources ?? {})
    .sort((a, b) => b[1] - a[1]).slice(0, 3), [profile])
  const maxWeight = Math.max(1, ...topTopics.map(([, w]) => Math.abs(w)))
  return (
    <>
      <section className="rounded-lg border border-border bg-surface/40 p-3">
        <h3 className="text-[10px] font-semibold uppercase tracking-wide text-muted">Mode</h3>
        <div className="mt-2"><ModeControl mode={mode} setMode={setMode} /></div>
        <p className="mt-2 text-[10px] leading-4 text-muted">
          {mode === 'for_you' ? 'Ranked by your actions with diversity caps — never an LLM at read time.' : 'Pure recency from the same snapshot.'}
        </p>
      </section>

      <section className="rounded-lg border border-border bg-surface/40 p-3">
        <h3 className="text-[10px] font-semibold uppercase tracking-wide text-muted">Source</h3>
        <div className="mt-2 flex flex-wrap gap-1.5">
          <button onClick={() => setSource('')}
            className={`rounded-md border px-2 py-1 text-[11px] ${source === '' ? 'border-accent bg-accent/10 text-accent' : 'border-border text-muted hover:text-text'}`}>All</button>
          {sources.map(src => (
            <button key={src.source} onClick={() => setSource(src.source === source ? '' : src.source)}
              className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] ${source === src.source ? 'border-accent bg-accent/10 text-accent' : 'border-border text-muted hover:text-text'}`}>
              <SourceLogo name={src.source} size={11} variant="inline" /> {src.source}
            </button>
          ))}
        </div>
      </section>

      <section className="rounded-lg border border-border bg-surface/40 p-3">
        <div className="flex items-center gap-1.5">
          <Brain size={12} className="text-accent" />
          <h3 className="text-[10px] font-semibold uppercase tracking-wide text-muted">What TOBI learned</h3>
        </div>
        {!profile || profile.version === 0 ? (
          <p className="mt-2 text-[11px] leading-4 text-muted">No interest profile yet — like, favorite, or note items and the next refresh builds one from those actions only.</p>
        ) : (
          <div className="mt-2 space-y-2">
            {topTopics.map(([topic, weight]) => (
              <div key={topic}>
                <div className="flex items-center justify-between text-[11px]">
                  <span className="truncate text-text/85">{topic}</span>
                  <span className="ml-2 shrink-0 font-mono text-muted">{weight > 0 ? '+' : ''}{weight.toFixed(1)}</span>
                </div>
                <div className="mt-0.5 h-1 overflow-hidden rounded-full bg-background/70">
                  <div className={weight >= 0 ? 'h-full rounded-full bg-accent/70' : 'h-full rounded-full bg-danger/50'}
                    style={{ width: `${Math.round((Math.abs(weight) / maxWeight) * 100)}%` }} />
                </div>
              </div>
            ))}
            {topSources.length > 0 && (
              <p className="pt-1 text-[10px] leading-4 text-muted">
                Preferred sources: {topSources.map(([name]) => name).join(', ')}
              </p>
            )}
            <p className="flex items-center gap-1 pt-1 text-[10px] text-muted">
              <Sparkles size={10} /> v{profile.version} · from {String((profile.provenance as Record<string, unknown>)?.items_considered ?? 0)} items · your actions only
            </p>
          </div>
        )}
      </section>
    </>
  )
}

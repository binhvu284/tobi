// News V2 Trending tab (#23, N09 + owner QA rounds).
// 1. GitHub growth table — growth ONLY from persisted snapshots, calm collecting state.
// 2. Tool Discovery — SHOPPING UX (owner direction): one product card (visual tile,
//    badges, description, like/dislike/favorite/note through the N06 contract) with
//    an "Explore next tool" cycle that refreshes only this section.
// 3. Source Explore — compact source filter in the header, exactly 3 news cards
//    (quality over quantity), "Explore more" pages this section only.
// Visual tiles are deterministic decorative gradients until the media pipeline fills
// news_media_cache — never a fake screenshot presented as content.
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  AlertTriangle, ChevronRight, ExternalLink, Github, Loader2, RefreshCw, Search,
  Sparkles, Star, StickyNote, ThumbsDown, ThumbsUp, TrendingUp, Undo2, Wrench,
} from 'lucide-react'
import { ActionButton } from '../async-ui'
import { getNewsV2Feed, getNewsV2TrendingGithub, getNewsV2TrendingSources, getNewsV2TrendingTools, patchNewsV2Interaction, postNewsV2Event, putNewsV2Note, type NewsV2GithubEntry, type NewsV2Interaction, type NewsV2ItemEntry } from '../../api.explore'
import { useToast } from '../../context/ToastProvider'
import SourceLogo from '../SourceLogo'
import SourceIconGroup from './SourceIconGroup'
import { DEFAULT_INTERACTION, cleanExcerpt } from './NewsCard'
import { RefreshIconButton, TableSkeleton, useTableRefresh } from './TableRefresh'
import RichText from './RichText'
import ActionBar from './ActionBar'

type Window = 'week' | 'month' | 'all'

// Mirrors the server-side facet (api/routers/news_v2.py). The dropdown filters the loaded
// board by topic; the server owns the classification so the two can never drift.
const TOPICS = ['All topics', 'AI/ML', 'Learn', 'Web', 'Mobile', 'Data', 'DevOps', 'Systems', 'Other']

function ago(iso: string | null | undefined): string {
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

function fmtStars(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(n >= 10_000 ? 0 : 1)}k` : String(n)
}

/** Same de-emphasis ladder as the Home Top 10 (plan §8: ordered Top-3 tables). */
function rankTone(rank: number) {
  if (rank === 1) return { row: 'bg-accent/[0.06]', badge: 'bg-accent text-background' }
  if (rank === 2) return { row: 'bg-accent/[0.03]', badge: 'border border-accent/50 text-accent' }
  if (rank === 3) return { row: '', badge: 'border border-accent/25 text-accent/80' }
  return { row: '', badge: 'border border-border text-muted' }
}

/** Deterministic decorative tile (per-item gradient + source badge). Renders the real
 *  cached media when a validated media_key exists; otherwise a labeled visual — never
 *  a fabricated screenshot. */
function VisualTile({ name, source, mediaKey, className }: {
  name: string; source: string; mediaKey?: string | null; className?: string
}) {
  const hue = [...name].reduce((acc, ch) => (acc * 31 + ch.charCodeAt(0)) % 360, 7)
  if (mediaKey) {
    return (
      <div className={`overflow-hidden bg-background/50 ${className ?? ''}`}>
        <img src={`/api/explore/v2/media/${mediaKey}`} alt="" loading="lazy"
          className="h-full w-full object-cover"
          onError={event => { event.currentTarget.style.display = 'none' }} />
      </div>
    )
  }
  return (
    <div className={`relative flex items-center justify-center overflow-hidden ${className ?? ''}`}
      style={{ background: `linear-gradient(135deg, hsl(${hue} 40% 30%), hsl(${(hue + 45) % 360} 50% 14%))` }}>
      <span className="select-none text-3xl font-bold text-white/25">{(name.trim()[0] || '?').toUpperCase()}</span>
      <span className="absolute bottom-1.5 right-1.5 flex h-6 w-6 items-center justify-center rounded-full border border-white/20 bg-black/30">
        <SourceLogo name={source} size={12} variant="inline" />
      </span>
    </div>
  )
}

export default function TrendingTab({ reloadKey }: { reloadKey: number }) {
  const [window_, setWindow] = useState<Window>('week')
  const [query, setQuery] = useState('')
  const [topic, setTopic] = useState('All topics')
  const [github, setGithub] = useState<NewsV2GithubEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (win: Window, q: string, top: string) => {
    setLoading(true)
    try {
      const gh = await getNewsV2TrendingGithub(win, q, top)
      setGithub(gh.entries)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally { setLoading(false) }
  }, [])
  useEffect(() => {                       // debounce the search so typing doesn't hammer the API
    const t = setTimeout(() => void load(window_, query, topic), query ? 250 : 0)
    return () => clearTimeout(t)
  }, [load, window_, query, topic, reloadKey])

  const { refreshing, refresh } = useTableRefresh('trending', GITHUB_SOURCES,
    useCallback(() => load(window_, query, topic), [load, window_, query, topic]))

  if (error) {
    return (
      <section className="mx-auto max-w-xl rounded-lg border border-danger/40 bg-danger/5 px-5 py-6 text-center">
        <AlertTriangle size={18} className="mx-auto text-danger" />
        <p className="mt-2 text-sm text-text">Trending data is unavailable.</p>
        <p className="mt-1 text-xs text-muted">{error}</p>
        <ActionButton onAction={() => load(window_, query, topic)} icon={<RefreshCw size={13} />} className="mt-4 inline-flex h-8 items-center gap-2 rounded-md border border-border px-3 text-xs text-text hover:bg-overlay/5"> Retry</ActionButton>
      </section>
    )
  }

  return (
    <div className="space-y-4">
      {/* ── 1. GitHub trending — REAL github.com/trending numbers ── */}
      <section className="overflow-hidden rounded-lg border border-border bg-surface/40">
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2.5">
          <div className="flex items-center gap-2"><Github size={14} className="text-accent" /><h2 className="text-xs font-semibold text-text">GitHub</h2><SourceIconGroup sources={['github']} size={16} /></div>
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search size={12} className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-muted" />
              <input value={query} onChange={event => setQuery(event.target.value)}
                placeholder="Search name / author" aria-label="Search repositories by name or author"
                className="h-7 w-40 rounded-md border border-border bg-background pl-7 pr-2 text-[11px] text-text outline-none focus:border-accent" />
            </div>
            <select value={topic} onChange={event => setTopic(event.target.value)}
              aria-label="Filter by topic"
              className="h-7 rounded-md border border-border bg-background px-2 text-[11px] font-medium text-text outline-none focus:border-accent">
              {TOPICS.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
            <select value={window_} onChange={event => setWindow(event.target.value as Window)}
              aria-label="Trending window"
              className="h-7 rounded-md border border-border bg-background px-2 text-[11px] font-medium text-text outline-none focus:border-accent">
              <option value="week">This week</option>
              <option value="month">This month</option>
              <option value="all">All time</option>
            </select>
            <RefreshIconButton refreshing={refreshing} onClick={refresh} />
          </div>
        </header>
        {refreshing || (loading && github.length === 0) ? (
          <TableSkeleton rows={5} />
        ) : github.length === 0 ? (
          <p className="px-4 py-8 text-center text-xs text-muted">
            {query ? `No trending repositories match “${query}”.`
              : topic !== 'All topics' ? `No ${topic} repositories in this window.`
              : 'No trending repositories yet — refresh to pull github.com/trending.'}
          </p>
        ) : (
          <div className="max-h-[520px] divide-y divide-border/60 overflow-y-auto">
            {github.map((entry, index) => {
              const tone = rankTone(index + 1)
              return (
                <div key={entry.repo} className={`flex items-center gap-3 px-4 py-2 ${tone.row}`}>
                  <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ${tone.badge}`}>{index + 1}</span>
                  <div className="min-w-0 flex-1">
                    <a href={`https://github.com/${entry.repo}`} target="_blank" rel="noreferrer"
                      className="block truncate text-sm font-medium text-text hover:text-accent">{entry.repo}</a>
                    <div className="mt-0.5 flex items-center gap-2">
                      {entry.language && <span className="shrink-0 text-[10px] font-medium text-muted/80">{entry.language}</span>}
                      {entry.description && (
                        <p className="truncate text-[11px] leading-4 text-muted" title={entry.description}>{entry.description}</p>
                      )}
                    </div>
                  </div>
                  {window_ !== 'all' && entry.growth !== undefined && (
                    <span title={`real stars gained this ${window_}, per github.com/trending`}
                      className="inline-flex w-16 shrink-0 items-center justify-end gap-1 text-xs font-semibold text-success">
                      <TrendingUp size={12} /> {entry.growth >= 0 ? '+' : ''}{fmtStars(entry.growth)}
                    </span>
                  )}
                  <span className="inline-flex w-14 shrink-0 items-center justify-end gap-1 text-xs text-muted"><Star size={11} /> {fmtStars(entry.stars)}</span>
                  {entry.item_id !== undefined && (
                    <ActionBar itemId={entry.item_id} interaction={entry.interaction} size="xs" actions={['favorite', 'note']} />
                  )}
                </div>
              )
            })}
          </div>
        )}
      </section>

      <ToolDiscovery reloadKey={reloadKey} />
      <SourceExplore reloadKey={reloadKey} />
    </div>
  )
}

const GITHUB_SOURCES = ['github']

// ── 2. Tool Discovery: shopping UX — one product at a time ───────────────────────────
function ToolDiscovery({ reloadKey }: { reloadKey: number }) {
  const { toast } = useToast()
  const [tools, setTools] = useState<NewsV2ItemEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [overrides, setOverrides] = useState<Record<number, NewsV2Interaction>>({})
  const [undoUntil, setUndoUntil] = useState<number | null>(null)
  const [, setTick] = useState(0)
  const [noteOpen, setNoteOpen] = useState(false)
  const [draft, setDraft] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getNewsV2TrendingTools()
      setTools(res.entries)
    } catch { setTools([]) } finally { setLoading(false) }
  }, [])
  useEffect(() => { void load() }, [load, reloadKey])

  // owner: "replace explore-next by a header refresh icon" — a scoped refresh runs the
  // content-creator (github + HN sources), which may take a while; skeleton covers it.
  const { refreshing, refresh } = useTableRefresh('trending', TOOL_SOURCES, load)

  // The refresh now resolves as soon as DATA is ready (fast); the LLM spotlight lands a
  // few seconds later in the backend's background phase. While the top pick still has no
  // recap, re-fetch a few times so the rich card upgrades itself — no second manual
  // refresh — then stop (bounded, never polls forever).
  const spotlightPoll = useRef(0)
  useEffect(() => { spotlightPoll.current = 0 }, [reloadKey, refreshing])
  useEffect(() => {
    const top = tools[0]
    if (!top || top.recap || refreshing || spotlightPoll.current >= 4) return
    const timer = setTimeout(() => { spotlightPoll.current += 1; void load() }, 12_000)
    return () => clearTimeout(timer)
  }, [tools, refreshing, load])

  // owner: "1 quality tool at a time" — show only the newest spotlight; refresh = next.
  const tool = tools.length ? tools[0] : null
  const ix = tool ? (overrides[tool.item_id] ?? tool.interaction ?? DEFAULT_INTERACTION) : DEFAULT_INTERACTION

  const next = () => { setNoteOpen(false); setUndoUntil(null); void refresh() }

  const mutate = async (action: 'like' | 'dislike' | 'undo' | 'favorite' | 'unfavorite') => {
    if (!tool || busy) return
    setBusy(action)
    try {
      const state = await patchNewsV2Interaction(tool.item_id, action, ix.version)
      setOverrides(current => ({ ...current, [tool.item_id]: state }))
      if (action === 'dislike') setUndoUntil(Date.now() + 10_000)
      if (action === 'undo') setUndoUntil(null)
    } catch (err) {
      toast({ kind: 'error', title: 'Action failed', detail: err instanceof Error ? err.message : String(err) })
    } finally { setBusy(null) }
  }

  useEffect(() => {                                     // dislike undo countdown → auto-next
    if (!undoUntil) return
    const timer = window.setInterval(() => {
      if (Date.now() >= undoUntil) { window.clearInterval(timer); next() }
      else setTick(k => k + 1)
    }, 250)
    return () => window.clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [undoUntil])

  const saveNote = async (clear: boolean) => {
    if (!tool || busy) return
    setBusy('note')
    try {
      const text = clear ? null : (draft.trim() || null)
      const state = await putNewsV2Note(tool.item_id, text, ix.version)
      setOverrides(current => ({ ...current, [tool.item_id]: state }))
      setNoteOpen(false)
      toast({ kind: 'success', title: text ? 'Note saved' : 'Note cleared' })
    } catch (err) {
      toast({ kind: 'error', title: 'Note not saved', detail: err instanceof Error ? err.message : String(err) })
    } finally { setBusy(null) }
  }

  const recordOpen = () => {
    if (!tool) return
    void postNewsV2Event(tool.item_id, { type: 'open' })
      .then(state => setOverrides(current => ({ ...current, [tool.item_id]: state })))
      .catch(() => {})
  }

  return (
    <section className="overflow-hidden rounded-lg border border-border bg-surface/40">
      <header className="flex h-11 items-center gap-2 border-b border-border px-4">
        <Wrench size={14} className="text-accent" /><h2 className="text-xs font-semibold text-text">Tool Discovery</h2>
        <SourceIconGroup sources={TOOL_SOURCES} size={16} />
        <p className="ml-auto hidden text-[11px] text-muted sm:block">A researched pick — like it, save it, or refresh for the next</p>
        <div className="ml-auto sm:ml-2"><RefreshIconButton refreshing={refreshing} onClick={refresh} title="Research the next tool" /></div>
      </header>
      {refreshing || loading ? (
        <TableSkeleton rows={4} className="p-4" />
      ) : !tool ? (
        <p className="px-4 py-8 text-center text-xs text-muted">No tool spotlight yet — hit refresh to research one.</p>
      ) : (
        <div className="p-4">
          <div className="grid gap-4 md:grid-cols-[230px,1fr]">
            <div>
              <VisualTile name={tool.title} source={tool.source} mediaKey={tool.media_key}
                className="aspect-video rounded-lg border border-border md:aspect-[4/3]" />
              <a href={tool.url} target="_blank" rel="noreferrer" onClick={recordOpen}
                className="mt-2.5 inline-flex h-9 w-full items-center justify-center gap-2 rounded-md border border-border text-xs font-semibold text-text transition-colors hover:border-accent/50 hover:text-accent">
                <ExternalLink size={13} /> Open
              </a>
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent">Tool</span>
                <span className="inline-flex items-center gap-1.5 rounded-full border border-border px-2 py-0.5 text-[10px] text-muted">
                  <SourceLogo name={tool.source} size={10} variant="inline" /> {tool.source}
                </span>
                {typeof tool.engagement === 'number' && tool.engagement > 0 && (
                  <span className="rounded-full border border-border px-2 py-0.5 text-[10px] text-muted">▲ {tool.engagement}</span>
                )}
                <span className="ml-auto text-[10px] text-muted">{ago(tool.published_at ?? tool.first_seen_at)}</span>
              </div>
              <h3 className="mt-2 text-base font-semibold leading-snug text-text">
                <a href={tool.url} target="_blank" rel="noreferrer" onClick={recordOpen} className="hover:text-accent">{tool.title}</a>
              </h3>
              {tool.recap ? (
                <div className="mt-2">
                  <span className="mb-1 inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-accent/80"><Sparkles size={10} /> TOBI spotlight</span>
                  <RichText text={tool.recap} />
                </div>
              ) : (
                <div className="mt-2">
                  {cleanExcerpt(tool.excerpt) && (
                    <p className="line-clamp-4 text-xs leading-5 text-muted">{cleanExcerpt(tool.excerpt)}</p>
                  )}
                  <span className="mt-1.5 inline-flex items-center gap-1 text-[10px] text-muted/70">
                    <Loader2 size={10} className="animate-spin" /> TOBI is researching a deeper spotlight — refresh in a moment.
                  </span>
                </div>
              )}
              {undoUntil && ix.reaction === 'dislike' ? (
                <div className="mt-3 flex items-center gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-2">
                  <span className="min-w-0 flex-1 text-xs text-text">Not for you — showing the next tool shortly.</span>
                  <button onClick={() => void mutate('undo')} disabled={busy !== null}
                    className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md border border-border bg-background px-2.5 text-xs font-medium text-text hover:border-accent/50 disabled:opacity-50">
                    {busy === 'undo' ? <Loader2 size={12} className="animate-spin" /> : <Undo2 size={12} />}
                    Undo ({Math.max(0, Math.ceil((undoUntil - Date.now()) / 1000))}s)
                  </button>
                </div>
              ) : (
                <div className="mt-3 flex flex-wrap items-center gap-1.5">
                  <ProductAction label="Like" active={ix.reaction === 'like'} busy={busy === 'like'}
                    onClick={() => void mutate('like')} icon={<ThumbsUp size={13} className={ix.reaction === 'like' ? 'fill-current' : ''} />} />
                  <ProductAction label="Dislike" active={false} busy={busy === 'dislike'}
                    onClick={() => void mutate('dislike')} icon={<ThumbsDown size={13} />} />
                  <ProductAction label={ix.favorite === 1 ? 'Saved' : 'Favorite'} active={ix.favorite === 1}
                    busy={busy === 'favorite' || busy === 'unfavorite'}
                    onClick={() => void mutate(ix.favorite === 1 ? 'unfavorite' : 'favorite')}
                    icon={<Star size={13} className={ix.favorite === 1 ? 'fill-current' : ''} />} />
                  <ProductAction label="Note" active={Boolean((ix.note ?? '').trim())} busy={false}
                    onClick={() => { setDraft(ix.note ?? ''); setNoteOpen(open => !open) }}
                    icon={<StickyNote size={13} />} />
                  {(ix.favorite === 1 || (ix.note ?? '').trim()) && (
                    <span title="Favorites and notes never expire" className="ml-1 inline-flex items-center gap-1 text-[10px] text-accent/80"><Sparkles size={10} /> kept forever</span>
                  )}
                </div>
              )}
              {noteOpen && (
                <div className="mt-3 rounded-md border border-border bg-background/60 p-2.5">
                  <textarea value={draft} onChange={event => setDraft(event.target.value)} rows={2}
                    placeholder="Private note about this tool"
                    className="w-full resize-y rounded-md border border-border bg-background px-2.5 py-2 text-xs text-text outline-none focus:border-accent" />
                  <div className="mt-2 flex items-center justify-end gap-2">
                    {(ix.note ?? '').trim() && (
                      <button onClick={() => void saveNote(true)} disabled={busy !== null}
                        className="inline-flex h-7 items-center rounded-md px-2.5 text-[11px] text-muted hover:text-danger disabled:opacity-50">Clear</button>
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
          </div>
        </div>
      )}
    </section>
  )
}

const TOOL_SOURCES = ['github', 'hackernews']

function ProductAction({ label, icon, active, busy, onClick }: {
  label: string; icon: React.ReactNode; active: boolean; busy: boolean; onClick: () => void
}) {
  return (
    <button onClick={onClick} disabled={busy}
      className={`inline-flex h-8 items-center gap-1.5 rounded-md border px-3 text-[11px] font-medium transition-colors disabled:opacity-50 ${
        active ? 'border-accent/50 bg-accent/10 text-accent' : 'border-border text-muted hover:border-accent/30 hover:text-text'}`}>
      {busy ? <Loader2 size={12} className="animate-spin" /> : icon} {label}
    </button>
  )
}

// ── 3. Source Explore: compact header filter + exactly 3 quality cards ───────────────
const EXPLORE_CARDS = 3
const EXPLORE_SOURCES = ['rss', 'hackernews']

function SourceExplore({ reloadKey }: { reloadKey: number }) {
  const [sources, setSources] = useState<{ source: string; items: number; latest_observed: string }[]>([])
  const [selected, setSelected] = useState('')          // '' = all sources
  const [items, setItems] = useState<NewsV2ItemEntry[]>([])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    void getNewsV2TrendingSources().then(res => setSources(res.sources)).catch(() => {})
  }, [reloadKey])

  // owner: "only 3 quality items at a time" — the freshest picks; refresh rotates them.
  const loadItems = useCallback(async (source: string) => {
    setBusy(true)
    try {
      const page = await getNewsV2Feed({ mode: 'latest', source: source || undefined, limit: EXPLORE_CARDS })
      setItems(page.entries.slice(0, EXPLORE_CARDS))
    } catch { setItems([]) } finally { setBusy(false) }
  }, [])
  useEffect(() => { void loadItems(selected) }, [loadItems, selected, reloadKey])

  const { refreshing, refresh } = useTableRefresh('feed', EXPLORE_SOURCES,
    useCallback(async () => {
      await getNewsV2TrendingSources().then(res => setSources(res.sources)).catch(() => {})
      await loadItems(selected)
    }, [loadItems, selected]))

  const visible = items.slice(0, EXPLORE_CARDS)
  if (!sources.length) return null

  return (
    <section className="overflow-hidden rounded-lg border border-border bg-surface/40">
      <header className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2">
        <h2 className="text-xs font-semibold text-text">Source Explore</h2>
        <div className="ml-auto flex items-center gap-1.5">
          <button onClick={() => setSelected('')} title="All sources"
            className={`inline-flex h-7 items-center rounded-full border px-2.5 text-[11px] font-medium transition-colors ${selected === '' ? 'border-accent bg-accent/10 text-accent' : 'border-border text-muted hover:text-text'}`}>
            All
          </button>
          {sources.map(src => (
            <button key={src.source} onClick={() => setSelected(src.source === selected ? '' : src.source)}
              title={`${src.source} · ${src.items} items · latest ${ago(src.latest_observed)}`}
              className={`flex h-7 w-7 items-center justify-center rounded-full border transition-all ${selected === src.source ? 'border-accent bg-accent/10 ring-1 ring-accent/40' : 'border-border hover:border-accent/40'}`}>
              <SourceLogo name={src.source} size={13} variant="inline" />
            </button>
          ))}
          <span className="mx-0.5 h-5 w-px bg-border" />
          <RefreshIconButton refreshing={refreshing} onClick={refresh} title="Refresh source explore" />
        </div>
      </header>
      {refreshing || (busy && visible.length === 0) ? (
        <div className="grid gap-3 p-4 sm:grid-cols-3">{[0, 1, 2].map(i => (
          <div key={i} className="h-52 animate-pulse rounded-lg bg-overlay/10" />))}
        </div>
      ) : visible.length === 0 ? (
        <p className="px-4 py-8 text-center text-xs text-muted">No canonical items {selected ? `from ${selected}` : ''} yet — run a refresh first.</p>
      ) : (
        <div className="p-4">
          <div className="grid gap-3 sm:grid-cols-3">
            {visible.map(item => (
              <article key={item.item_id} className="flex flex-col overflow-hidden rounded-lg border border-border bg-surface/60 transition-colors hover:border-accent/30">
                <VisualTile name={item.title} source={item.source} mediaKey={item.media_key}
                  className="aspect-video" />
                <div className="flex flex-1 flex-col p-3">
                  <div className="flex items-center gap-1.5 text-[10px] text-muted">
                    <SourceLogo name={item.source} size={11} variant="inline" />
                    <span className="font-medium text-text/75">{item.source}</span>
                    <span className="ml-auto">{ago(item.published_at ?? item.first_seen_at)}</span>
                  </div>
                  <h3 className="mt-1.5 line-clamp-2 text-[13px] font-semibold leading-snug text-text">
                    <a href={item.url} target="_blank" rel="noreferrer" className="hover:text-accent">{item.title}</a>
                  </h3>
                  {cleanExcerpt(item.excerpt) && (
                    <p className="mt-1 line-clamp-4 text-[11px] leading-[1.35rem] text-muted">{cleanExcerpt(item.excerpt)}</p>
                  )}
                  <div className="mt-auto flex items-center justify-between gap-2 pt-2.5">
                    <a href={item.url} target="_blank" rel="noreferrer"
                      className="inline-flex items-center gap-1 text-[11px] font-medium text-muted transition-colors hover:text-accent">
                      <ExternalLink size={11} /> Open
                    </a>
                    <ActionBar itemId={item.item_id} interaction={item.interaction} size="xs" />
                  </div>
                </div>
              </article>
            ))}
          </div>
          <p className="mt-3 text-center text-[10px] text-muted/70">
            Three fresh picks each refresh — favourite one to keep it, the rest rotate out.
          </p>
        </div>
      )}
    </section>
  )
}

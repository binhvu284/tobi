// News V2 Trending tab (#23, N09): GitHub growth table → Tool Discovery → Source
// Explore (plan §8). The acceptance gate is honesty: growth renders ONLY when the
// backend computed it from persisted star snapshots — repos without a valid baseline
// show a "Collecting history" chip and never a number. Top-3 rows reuse the Home
// rank ladder (theme-token classes, no hardcoded colors).
import { useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle, ChevronRight, ExternalLink, Github, Hourglass, Loader2, RefreshCw, Star,
  TrendingUp, Wrench,
} from 'lucide-react'
import {
  getNewsV2Feed, getNewsV2TrendingGithub, getNewsV2TrendingSources, getNewsV2TrendingTools,
  type NewsV2GithubEntry, type NewsV2ItemEntry,
} from '../../api'
import SourceLogo from '../SourceLogo'
import SourceIconGroup from './SourceIconGroup'

type Window = 'week' | 'month' | 'all'

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

export default function TrendingTab({ reloadKey }: { reloadKey: number }) {
  const [window_, setWindow] = useState<Window>('week')
  const [github, setGithub] = useState<NewsV2GithubEntry[]>([])
  const [tools, setTools] = useState<NewsV2ItemEntry[]>([])
  const [sources, setSources] = useState<{ source: string; items: number; latest_observed: string }[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (win: Window) => {
    setLoading(true)
    try {
      const [gh, tl, src] = await Promise.all([
        getNewsV2TrendingGithub(win), getNewsV2TrendingTools(), getNewsV2TrendingSources(),
      ])
      setGithub(gh.entries); setTools(tl.entries); setSources(src.sources)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally { setLoading(false) }
  }, [])
  useEffect(() => { void load(window_) }, [load, window_, reloadKey])

  if (error) {
    return (
      <section className="mx-auto max-w-xl rounded-lg border border-danger/40 bg-danger/5 px-5 py-6 text-center">
        <AlertTriangle size={18} className="mx-auto text-danger" />
        <p className="mt-2 text-sm text-text">Trending data is unavailable.</p>
        <p className="mt-1 text-xs text-muted">{error}</p>
        <button onClick={() => void load(window_)} className="mt-4 inline-flex h-8 items-center gap-2 rounded-md border border-border px-3 text-xs text-text hover:bg-overlay/5"><RefreshCw size={13} /> Retry</button>
      </section>
    )
  }

  return (
    <div className="space-y-4">
      {/* ── 1. GitHub growth (snapshots only — collecting until history exists) ── */}
      <section className="overflow-hidden rounded-lg border border-border bg-surface/40">
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2.5">
          <div className="flex items-center gap-2"><Github size={14} className="text-accent" /><h2 className="text-xs font-semibold text-text">GitHub · AI repositories</h2><SourceIconGroup sources={['github']} size={16} /></div>
          <div className="flex overflow-hidden rounded-md border border-border">
            {(['week', 'month', 'all'] as Window[]).map(win => (
              <button key={win} onClick={() => setWindow(win)}
                className={`px-2.5 py-1 text-[11px] font-medium transition-colors ${window_ === win ? 'bg-accent text-background' : 'text-muted hover:text-text'}`}>
                {win === 'all' ? 'All time' : win === 'week' ? 'Week' : 'Month'}
              </button>
            ))}
          </div>
        </header>
        {loading && github.length === 0 ? (
          <div className="space-y-2 p-4">{[0, 1, 2].map(i => <div key={i} className="h-9 animate-pulse rounded-md bg-overlay/10" />)}</div>
        ) : github.length === 0 ? (
          <p className="px-4 py-8 text-center text-xs text-muted">No repository snapshots yet — run a Trending refresh to start collecting star history.</p>
        ) : (
          <>
          {github.every(entry => entry.growth === undefined) && (
            <p className="flex items-center gap-1.5 border-b border-border/60 bg-surface/30 px-4 py-1.5 text-[11px] text-muted">
              <Hourglass size={11} className="shrink-0" />
              Collecting star history — {window_ === 'all' ? 'all-time' : window_ === 'week' ? 'weekly' : 'monthly'} growth appears once daily snapshots span the window. Growth is never estimated.
            </p>
          )}
          <div className="divide-y divide-border/60">
            {github.map((entry, index) => {
              const tone = rankTone(index + 1)
              return (
                <div key={entry.repo} className={`flex items-center gap-3 px-4 py-2 ${tone.row}`}>
                  <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ${tone.badge}`}>{index + 1}</span>
                  <div className="min-w-0 flex-1">
                    <a href={`https://github.com/${entry.repo}`} target="_blank" rel="noreferrer"
                      className="block truncate text-sm font-medium text-text hover:text-accent">{entry.repo}</a>
                    {entry.description && (
                      <p className="mt-0.5 truncate text-[11px] leading-4 text-muted" title={entry.description}>{entry.description}</p>
                    )}
                  </div>
                  {entry.growth !== undefined ? (
                    <span title={`vs snapshot from ${entry.baseline_date}`}
                      className="inline-flex w-16 shrink-0 items-center justify-end gap-1 text-xs font-semibold text-success">
                      <TrendingUp size={12} /> +{fmtStars(entry.growth)}
                    </span>
                  ) : (
                    <span title="No persisted star history for this window yet — growth is never estimated"
                      className="w-16 shrink-0 text-right text-xs text-muted/50">—</span>
                  )}
                  <span className="inline-flex w-16 shrink-0 items-center justify-end gap-1 text-xs text-muted"><Star size={11} /> {fmtStars(entry.stars)}</span>
                </div>
              )
            })}
          </div>
          </>
        )}
      </section>

      {/* ── 2. Tool Discovery: one featured + alternatives ─────────────────────── */}
      <section className="overflow-hidden rounded-lg border border-border bg-surface/40">
        <header className="flex h-11 items-center gap-2 border-b border-border px-4"><Wrench size={14} className="text-accent" /><h2 className="text-xs font-semibold text-text">Tool Discovery</h2><SourceIconGroup sources={['hackernews']} size={16} /></header>
        {tools.length === 0 ? (
          <p className="px-4 py-8 text-center text-xs text-muted">No tool candidates yet — Show&nbsp;HN posts and repos land here after a refresh.</p>
        ) : (
          <div className="p-4">
            <FeaturedTool tool={tools[0]} />
            {tools.length > 1 && (
              <div className="mt-3 divide-y divide-border/50 border-t border-border/70">
                {tools.slice(1, 6).map(tool => (
                  <div key={tool.item_id} className="flex items-center gap-2.5 py-2">
                    <SourceLogo name={tool.source} size={12} variant="inline" />
                    <div className="min-w-0 flex-1">
                      <a href={tool.url} target="_blank" rel="noreferrer" className="block truncate text-sm text-text hover:text-accent">{tool.title}</a>
                      {tool.excerpt && (
                        <p className="mt-0.5 truncate text-[11px] leading-4 text-muted" title={tool.excerpt}>{tool.excerpt}</p>
                      )}
                    </div>
                    <span className="shrink-0 text-[11px] text-muted">{tool.engagement ? `▲ ${tool.engagement}` : tool.source}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </section>

      {/* ── 3. Source Explore: canonical-store projection ──────────────────────── */}
      <SourceExplore sources={sources} />
    </div>
  )
}

function FeaturedTool({ tool }: { tool: NewsV2ItemEntry }) {
  return (
    <div className="rounded-md border border-accent/25 bg-accent/[0.05] p-3.5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[9px] font-semibold uppercase tracking-wide text-accent">Featured</div>
          <a href={tool.url} target="_blank" rel="noreferrer" className="mt-1 block truncate text-sm font-semibold text-text hover:text-accent">{tool.title}</a>
          <div className="mt-1 flex items-center gap-2 text-[11px] text-muted">
            <SourceLogo name={tool.source} size={11} variant="inline" /> {tool.source}
            {tool.engagement ? <span>· ▲ {tool.engagement}</span> : null}
          </div>
        </div>
        <a href={tool.url} target="_blank" rel="noreferrer" title="Open"
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border text-muted hover:text-accent"><ExternalLink size={14} /></a>
      </div>
      {tool.excerpt && <p className="mt-2 line-clamp-2 text-xs leading-5 text-muted">{tool.excerpt}</p>}
    </div>
  )
}

function SourceExplore({ sources }: { sources: { source: string; items: number; latest_observed: string }[] }) {
  const [selected, setSelected] = useState<string | null>(null)
  const [items, setItems] = useState<NewsV2ItemEntry[]>([])
  const [busy, setBusy] = useState(false)

  const openSource = async (source: string) => {
    if (selected === source) { setSelected(null); return }
    setSelected(source); setBusy(true); setItems([])
    try {
      const page = await getNewsV2Feed({ mode: 'latest', source, limit: 15 })
      setItems(page.entries)
    } catch { setItems([]) } finally { setBusy(false) }
  }

  if (!sources.length) return null
  return (
    <section className="overflow-hidden rounded-lg border border-border bg-surface/40">
      <header className="flex h-11 items-center gap-2 border-b border-border px-4">
        <SourceIconGroup sources={sources.map(src => src.source)} size={16} />
        <h2 className="text-xs font-semibold text-text">Source Explore</h2>
        <p className="ml-auto hidden text-[11px] text-muted sm:block">Browse everything collected, per source</p>
      </header>
      <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3">
        {sources.map(src => (
          <button key={src.source} onClick={() => void openSource(src.source)}
            className={`flex items-center gap-3 rounded-lg border p-3 text-left transition-colors ${selected === src.source ? 'border-accent bg-accent/[0.06]' : 'border-border hover:border-accent/40'}`}>
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-border bg-background">
              <SourceLogo name={src.source} size={16} variant="inline" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-text">{src.source}</span>
              <span className="block text-[11px] text-muted">{src.items} items · latest {ago(src.latest_observed)}</span>
            </span>
            <ChevronRight size={14} className={`shrink-0 transition-transform ${selected === src.source ? 'rotate-90 text-accent' : 'text-muted'}`} />
          </button>
        ))}
      </div>
      {selected && (
        <div className="border-t border-border/70 px-4 py-3">
          {busy ? (
            <div className="flex items-center gap-2 py-4 text-xs text-muted"><Loader2 size={13} className="animate-spin" /> Loading {selected}…</div>
          ) : items.length === 0 ? (
            <p className="py-4 text-center text-xs text-muted">No canonical items from {selected} in the current snapshot.</p>
          ) : (
            <div className="divide-y divide-border/50">
              {items.map(item => (
                <div key={item.item_id} className="flex items-center gap-2.5 py-2">
                  <div className="min-w-0 flex-1">
                    <a href={item.url} target="_blank" rel="noreferrer" className="block truncate text-sm text-text hover:text-accent">{item.title}</a>
                    {item.excerpt && (
                      <p className="mt-0.5 truncate text-[11px] leading-4 text-muted" title={item.excerpt}>{item.excerpt}</p>
                    )}
                  </div>
                  <span className="shrink-0 text-[11px] text-muted">{ago(item.published_at ?? item.first_seen_at)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  )
}

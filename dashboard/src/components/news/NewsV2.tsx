// News V2 shell (#23, N07) + Home tab (N08).
// Four-tab operational shell over /api/explore/v2. Rank styling uses News-scoped
// CSS variables mapped from the ACTIVE theme tokens (--news-rank-*: var(--accent))
// — never hardcoded colors — so every installed theme renders the #1..#3 hierarchy;
// motion is gated with motion-safe so Reduced/Off keeps badge/border/type hierarchy.
// Trending (N09) and Feed/Favorites (N10) render their own tab components.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Activity, AlertTriangle, ExternalLink, Loader2, Maximize2, Newspaper,
  RefreshCw, Rss, Search, Star, TrendingUp, Trophy, X,
} from 'lucide-react'
import {
  getNewsV2Home, getNewsV2Models, getNewsV2RefreshJob, postNewsV2Refresh,
  type NewsV2Home, type NewsV2ModelMetric, type NewsV2RankEntry, type NewsV2Release,
} from '../../api'
import { useToast } from '../../context/ToastProvider'
import LlmLogo from '../LlmLogo'
import TrendingTab from './TrendingTab'
import FeedTab from './FeedTab'
import FavoritesTab from './FavoritesTab'

type V2Tab = 'home' | 'trending' | 'feed' | 'favorites'

const TABS: { id: V2Tab; label: string; icon: React.ReactNode }[] = [
  { id: 'home', label: 'Home', icon: <Trophy size={13} /> },
  { id: 'trending', label: 'Trending', icon: <TrendingUp size={13} /> },
  { id: 'feed', label: 'News Feed', icon: <Rss size={13} /> },
  { id: 'favorites', label: 'Favorites', icon: <Star size={13} /> },
]

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

export default function NewsV2() {
  const { toast } = useToast()
  const [tab, setTab] = useState<V2Tab>('home')
  const [home, setHome] = useState<NewsV2Home | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)     // bumped after a refresh job lands
  const pollTimer = useRef<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setHome(await getNewsV2Home())
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally { setLoading(false) }
  }, [])
  useEffect(() => { void load() }, [load])
  useEffect(() => () => { if (pollTimer.current) window.clearInterval(pollTimer.current) }, [])

  const refresh = async () => {
    if (refreshing || tab === 'favorites') return
    setRefreshing(true)
    try {
      const started = await postNewsV2Refresh(tab === 'home' ? 'home' : tab === 'trending' ? 'trending' : 'feed')
      pollTimer.current = window.setInterval(async () => {
        try {
          const job = await getNewsV2RefreshJob(started.job_id)
          if (['completed', 'partial', 'failed', 'canceled'].includes(job.state)) {
            if (pollTimer.current) window.clearInterval(pollTimer.current)
            setRefreshing(false)
            if (job.state === 'failed') toast({ kind: 'error', title: 'Refresh failed', detail: job.error ?? undefined })
            else if (job.state === 'partial') toast({ kind: 'info', title: 'Refresh finished with some sources failing', detail: job.error ?? undefined })
            else toast({ kind: 'success', title: 'Refreshed' })
            setReloadKey(current => current + 1)
            void load()
          }
        } catch { /* job briefly unavailable — keep polling until the cap */ }
      }, 800)
    } catch (err) {
      setRefreshing(false)
      toast({ kind: 'error', title: 'Refresh did not start', detail: err instanceof Error ? err.message : String(err) })
    }
  }

  const freshest = useMemo(() => {
    const values = Object.values(home?.freshness ?? {})
    return values.length ? values.sort().slice(-1)[0] : null
  }, [home])

  return (
    <div className="news-v2 min-h-full">
      {/* News-scoped rank variables mapped from the active theme tokens (plan §8) */}
      <style>{`.news-v2{--news-rank-1:var(--accent);--news-rank-2:var(--accent);--news-rank-3:var(--accent);}`}</style>

      <header className="sticky top-0 z-20 border-b border-border bg-background/90 backdrop-blur-xl">
        <div className="flex items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-accent/30 bg-accent/10 text-accent"><Newspaper size={18} /></div>
            <div className="min-w-0">
              <h1 className="truncate text-lg font-semibold text-text">News</h1>
              <p className="mt-0.5 truncate text-[11px] text-muted">Personalized AI intelligence · V2</p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {freshest && <span className="hidden items-center gap-1.5 rounded-full border border-border px-2 py-1 text-[10px] text-muted sm:inline-flex"><Activity size={11} /> data {ago(freshest)}</span>}
            {tab !== 'favorites' && (
              <button onClick={refresh} disabled={refreshing} title={`Refresh the ${tab} tab now`}
                className="inline-flex h-9 items-center gap-2 rounded-md border border-border px-3 text-xs font-medium text-text hover:border-accent/40 disabled:opacity-50">
                <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} /> {refreshing ? 'Refreshing…' : 'Refresh'}
              </button>
            )}
          </div>
        </div>
        <nav aria-label="News sections" className="flex overflow-x-auto px-2 sm:px-4">
          {TABS.map(item => (
            <button key={item.id} onClick={() => setTab(item.id)}
              className={`inline-flex h-10 shrink-0 items-center gap-1.5 border-b-2 px-3 text-xs font-medium transition-colors ${tab === item.id ? 'border-accent text-accent' : 'border-transparent text-muted hover:text-text'}`}>
              {item.icon} {item.label}
            </button>
          ))}
        </nav>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
        {tab === 'home' && <HomeTab home={home} loading={loading} error={error} onRetry={load} />}
        {tab === 'trending' && <TrendingTab reloadKey={reloadKey} />}
        {tab === 'feed' && <FeedTab reloadKey={reloadKey} />}
        {tab === 'favorites' && <FavoritesTab />}
      </main>
    </div>
  )
}

// ── Home (N08): Model Strength Top 10 + Latest Releases, always sourced + timed ──────
function HomeTab({ home, loading, error, onRetry }: {
  home: NewsV2Home | null; loading: boolean; error: string | null; onRetry: () => void
}) {
  const [explorerOpen, setExplorerOpen] = useState(false)
  if (loading && !home) {
    return <div className="grid gap-4 xl:grid-cols-2">{[0, 1].map(i => (
      <div key={i} className="h-72 animate-pulse rounded-lg border border-border bg-surface/40" />))}
    </div>
  }
  if (error) {
    return (
      <section className="mx-auto max-w-xl rounded-lg border border-danger/40 bg-danger/5 px-5 py-6 text-center">
        <AlertTriangle size={18} className="mx-auto text-danger" />
        <p className="mt-2 text-sm text-text">News data is unavailable.</p>
        <p className="mt-1 text-xs text-muted">{error}</p>
        <button onClick={onRetry} className="mt-4 inline-flex h-8 items-center gap-2 rounded-md border border-border px-3 text-xs text-text hover:bg-overlay/5"><RefreshCw size={13} /> Retry</button>
      </section>
    )
  }
  const top10 = home?.top10 ?? []
  const releases = home?.releases ?? []
  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-2">
        <section className="overflow-hidden rounded-lg border border-border bg-surface/40">
          <header className="flex h-11 items-center justify-between border-b border-border px-4">
            <div className="flex items-center gap-2"><Trophy size={14} className="text-accent" /><h2 className="text-xs font-semibold text-text">Model Strength · Top 10</h2></div>
            <button onClick={() => setExplorerOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-[11px] text-muted hover:text-accent">
              <Maximize2 size={11} /> Explore models
            </button>
          </header>
          {top10.length === 0 ? (
            <p className="px-4 py-10 text-center text-xs text-muted">No model snapshot yet — run a Home refresh once model sources have been collected.</p>
          ) : (
            <div className="divide-y divide-border/60">
              {top10.map((entry, index) => <RankRow key={entry.model_id} entry={entry} rank={index + 1}
                maxScore={top10[0]?.score || 100} />)}
            </div>
          )}
        </section>

        <section className="overflow-hidden rounded-lg border border-border bg-surface/40">
          <header className="flex h-11 items-center gap-2 border-b border-border px-4"><Rss size={14} className="text-accent" /><h2 className="text-xs font-semibold text-text">Latest Releases</h2></header>
          {releases.length === 0 ? (
            <p className="px-4 py-10 text-center text-xs text-muted">No release evidence yet — releases appear once catalog sources report new models.</p>
          ) : (
            <div className="divide-y divide-border/60">{releases.map(release => <ReleaseRow key={release.id} release={release} />)}</div>
          )}
        </section>
      </div>

      <SourceHealth home={home} />
      <ModelExplorerModal open={explorerOpen} onClose={() => setExplorerOpen(false)} />
    </div>
  )
}

/** Rank hierarchy #1→#3 reduces in intensity; every treatment reads from the
 *  news-scoped variables (theme tokens) — bars/badges survive Reduced/Off motion. */
function RankRow({ entry, rank, maxScore }: { entry: NewsV2RankEntry; rank: number; maxScore: number }) {
  const pct = Math.max(6, Math.round((entry.score / Math.max(1, maxScore)) * 100))
  const tone = rank === 1
    ? { row: 'bg-accent/[0.06]', badge: 'bg-accent text-background', bar: 'bg-accent motion-safe:animate-pulse', name: 'font-semibold text-text' }
    : rank === 2
      ? { row: 'bg-accent/[0.03]', badge: 'border border-accent/50 text-accent', bar: 'bg-accent/80', name: 'font-medium text-text' }
      : rank === 3
        ? { row: '', badge: 'border border-accent/25 text-accent/80', bar: 'bg-accent/60', name: 'font-medium text-text' }
        : { row: '', badge: 'border border-border text-muted', bar: 'bg-overlay/30', name: 'text-text' }
  const evidence = `${entry.families} score families · sources: ${entry.sources.join(', ')} · ${entry.formula_version}`
  return (
    <div className={`flex items-center gap-3 px-4 py-2.5 ${tone.row}`} title={evidence}>
      <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ${tone.badge}`}>
        {rank === 1 ? <Trophy size={12} /> : rank}
      </span>
      <LlmLogo model={entry.model_id} size={14} className="h-6 w-6 border border-border bg-background" />
      <div className="min-w-0 flex-1">
        <div className={`truncate text-sm ${tone.name}`}>{entry.model_id}</div>
        <div className="mt-1 h-1.5 w-full max-w-[240px] overflow-hidden rounded-full bg-background/70">
          <div className={`h-full rounded-full ${tone.bar}`} style={{ width: `${pct}%` }} />
        </div>
      </div>
      <div className="shrink-0 text-right">
        <div className="font-mono text-sm font-semibold text-text">{entry.score.toFixed(1)}</div>
        <div className="text-[10px] text-muted">{entry.sources.length} source{entry.sources.length === 1 ? '' : 's'}</div>
      </div>
    </div>
  )
}

function ReleaseRow({ release }: { release: NewsV2Release }) {
  return (
    <div className="flex items-center gap-3 px-4 py-2.5">
      <LlmLogo model={release.model_id ?? undefined} size={14} className="h-6 w-6 border border-border bg-background" />
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm text-text">{release.title}</div>
        <div className="mt-0.5 text-[11px] text-muted">
          {release.released_at ? `released ${ago(release.released_at)}` : `observed ${ago(release.observed_at)}`}
        </div>
      </div>
      <a href={release.source_url} target="_blank" rel="noreferrer" title={release.source_url}
        className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted hover:text-accent">
        <ExternalLink size={13} />
      </a>
    </div>
  )
}

function SourceHealth({ home }: { home: NewsV2Home | null }) {
  const health = home?.source_health ?? {}
  const entries = Object.entries(health)
  if (!entries.length) return null
  return (
    <section className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-surface/30 px-4 py-3">
      <span className="text-[10px] font-semibold uppercase tracking-wide text-muted">Source health</span>
      {entries.map(([tabName, job]) => (
        <span key={tabName} title={job ? `updated ${ago(job.updated_at)}` : 'no refresh yet'}
          className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] ${!job ? 'border-border text-muted'
            : job.state === 'completed' ? 'border-success/40 bg-success/10 text-success'
              : job.state === 'partial' ? 'border-warning/40 bg-warning/10 text-warning'
                : job.state === 'failed' ? 'border-danger/40 bg-danger/10 text-danger'
                  : 'border-border text-muted'}`}>
          {tabName}: {job ? job.state : 'never'}
        </span>
      ))}
    </section>
  )
}

// ── Full-screen Model Explorer (N08): search + category, keyset pagination ───────────
function ModelExplorerModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [q, setQ] = useState('')
  const [category, setCategory] = useState('')
  const [models, setModels] = useState<{ model_id: string; metrics: NewsV2ModelMetric[] }[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)

  const search = useCallback(async (reset: boolean, cur?: string | null) => {
    setBusy(true)
    try {
      const page = await getNewsV2Models({ q, category, cursor: reset ? undefined : cur ?? undefined, limit: 20 })
      setModels(current => reset ? page.models : [...current, ...page.models])
      setCursor(page.next_cursor)
      setFailed(null)
    } catch (err) {
      setFailed(err instanceof Error ? err.message : String(err))
    } finally { setBusy(false) }
  }, [q, category])
  useEffect(() => { if (open) void search(true) }, [open, search])

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-50 bg-background/85 p-3 backdrop-blur-sm sm:p-6"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.section role="dialog" aria-modal="true" onClick={event => event.stopPropagation()}
            initial={{ opacity: 0, y: 14, scale: 0.99 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 10, scale: 0.99 }}
            transition={{ duration: 0.16 }}
            className="mx-auto flex h-full max-w-5xl flex-col rounded-lg border border-border bg-surface shadow-2xl">
            <header className="flex items-center justify-between gap-3 border-b border-border px-5 py-4">
              <div><h2 className="font-semibold text-text">Model Explorer</h2><p className="mt-0.5 text-xs text-muted">Every model with evidence — attributed metrics, not just the Top 10.</p></div>
              <button onClick={onClose} title="Close" className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted hover:bg-overlay/10 hover:text-text"><X size={17} /></button>
            </header>
            <div className="flex flex-wrap items-center gap-2 border-b border-border px-5 py-3">
              <div className="relative min-w-[220px] flex-1">
                <Search size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
                <input value={q} onChange={event => setQ(event.target.value)} placeholder="Search by model id"
                  onKeyDown={event => { if (event.key === 'Enter') void search(true) }}
                  className="h-9 w-full rounded-md border border-border bg-background pl-8 pr-3 text-sm text-text outline-none focus:border-accent" />
              </div>
              <select value={category} onChange={event => setCategory(event.target.value)}
                className="h-9 rounded-md border border-border bg-background px-2 text-xs text-text outline-none focus:border-accent">
                <option value="">All categories</option>
                <option value="general">General</option>
              </select>
              <button onClick={() => void search(true)} disabled={busy}
                className="inline-flex h-9 items-center gap-2 rounded-md bg-accent px-3 text-xs font-semibold text-background disabled:opacity-50">
                {busy ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />} Search
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
              {failed ? (
                <div className="flex items-center gap-2 rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger"><AlertTriangle size={13} /> {failed}</div>
              ) : models.length === 0 && !busy ? (
                <p className="py-12 text-center text-xs text-muted">No models match.</p>
              ) : (
                <div className="space-y-3">
                  {models.map(model => (
                    <section key={model.model_id} className="overflow-hidden rounded-md border border-border bg-surface/60">
                      <header className="flex items-center gap-2 border-b border-border/70 px-3 py-2">
                        <LlmLogo model={model.model_id} size={13} className="h-5 w-5 border border-border bg-background" />
                        <span className="truncate text-sm font-medium text-text">{model.model_id}</span>
                      </header>
                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-xs">
                          <thead><tr className="text-[10px] uppercase text-muted">
                            <th className="px-3 py-1.5">Metric</th><th className="px-3 py-1.5">Value</th>
                            <th className="px-3 py-1.5">Source</th><th className="px-3 py-1.5">Observed</th>
                            <th className="px-3 py-1.5">Confidence</th>
                          </tr></thead>
                          <tbody className="divide-y divide-border/50">
                            {model.metrics.map((metric, index) => (
                              <tr key={index}>
                                <td className="px-3 py-1.5 text-text">{metric.metric}</td>
                                <td className="px-3 py-1.5 font-mono text-text">{metric.value}</td>
                                <td className="px-3 py-1.5 text-muted">{metric.source}</td>
                                <td className="px-3 py-1.5 text-muted">{ago(metric.observed_at)}</td>
                                <td className="px-3 py-1.5 text-muted">{Math.round(metric.confidence * 100)}%</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </section>
                  ))}
                  {cursor && (
                    <button onClick={() => void search(false, cursor)} disabled={busy}
                      className="mx-auto flex h-9 items-center gap-2 rounded-md border border-border px-4 text-xs text-text hover:border-accent/40 disabled:opacity-50">
                      {busy ? <Loader2 size={13} className="animate-spin" /> : null} Load more
                    </button>
                  )}
                </div>
              )}
            </div>
          </motion.section>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  )
}

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
  Activity, AlertTriangle, Ban, Check, CircleDashed, ExternalLink, Loader2, Maximize2,
  Newspaper, RefreshCw, Rss, Search, Settings2, Star, TrendingUp, Trophy, X,
} from 'lucide-react'
import {
  getNewsV2Home, getNewsV2ModelLeaderboards, getNewsV2Models, getNewsV2RefreshJob,
  getNewsV2Settings, patchNewsV2Settings, postNewsV2Refresh, postNewsV2RefreshCommand,
  type NewsV2Home, type NewsV2Leaderboard, type NewsV2ModelMetric, type NewsV2RankEntry,
  type NewsV2RefreshJob, type NewsV2Release, type NewsV2Settings,
} from '../../api'
import { useToast } from '../../context/ToastProvider'
import LlmLogo from '../LlmLogo'
import SourceLogo from '../SourceLogo'
import SourceIconGroup from './SourceIconGroup'
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

/** Absolute time in the OWNER's local timezone (matches the header clock) — used
 *  as the tooltip behind every relative "Xh ago" so times are never ambiguous. */
function localTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const stamp = new Date(iso)
  return Number.isFinite(stamp.getTime()) ? stamp.toLocaleString() : String(iso)
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

  const [job, setJob] = useState<NewsV2RefreshJob | null>(null)   // live progress panel
  const [settings, setSettings] = useState<NewsV2Settings | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  useEffect(() => { void getNewsV2Settings().then(setSettings).catch(() => {}) }, [])

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

  // Poll the durable job row and keep it in state — the progress strip renders
  // per-source checkpoints live. Terminal partial/failed keeps the panel up with
  // a Retry-failed action instead of vanishing into a toast.
  const beginPolling = (jobId: number) => {
    if (pollTimer.current) window.clearInterval(pollTimer.current)
    pollTimer.current = window.setInterval(async () => {
      try {
        const current = await getNewsV2RefreshJob(jobId)
        setJob(current)
        if (['completed', 'partial', 'failed', 'canceled'].includes(current.state)) {
          if (pollTimer.current) window.clearInterval(pollTimer.current)
          setRefreshing(false)
          if (current.state === 'failed') toast({ kind: 'error', title: 'Refresh failed', detail: current.error ?? undefined })
          else if (current.state === 'partial') toast({ kind: 'info', title: 'Refresh finished with some sources failing', detail: current.error ?? undefined })
          else if (current.state === 'canceled') { toast({ kind: 'info', title: 'Refresh canceled' }); setJob(null) }
          else { toast({ kind: 'success', title: 'Refreshed' }); setJob(null) }
          setReloadKey(value => value + 1)
          void load()
        }
      } catch { /* job briefly unavailable — keep polling */ }
    }, 700)
  }

  const refresh = async () => {
    if (refreshing || tab === 'favorites') return
    setRefreshing(true)
    setJob(null)
    try {
      const started = await postNewsV2Refresh(tab === 'home' ? 'home' : tab === 'trending' ? 'trending' : 'feed')
      try { setJob(await getNewsV2RefreshJob(started.job_id)) } catch { /* first poll fills it */ }
      beginPolling(started.job_id)
    } catch (err) {
      setRefreshing(false)
      toast({ kind: 'error', title: 'Refresh did not start', detail: err instanceof Error ? err.message : String(err) })
    }
  }

  const retryFailed = async () => {
    if (!job || refreshing) return
    setRefreshing(true)
    try {
      setJob(await postNewsV2RefreshCommand(job.id, 'retry_failed'))
      beginPolling(job.id)
    } catch (err) {
      setRefreshing(false)
      toast({ kind: 'error', title: 'Retry did not start', detail: err instanceof Error ? err.message : String(err) })
    }
  }

  const cancelRefresh = async () => {
    if (!job) return
    try { await postNewsV2RefreshCommand(job.id, 'cancel') } catch { /* runner may have just finished */ }
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
            {freshest && <span title={localTime(freshest)} className="hidden items-center gap-1.5 rounded-full border border-border px-2 py-1 text-[10px] text-muted sm:inline-flex"><Activity size={11} /> data {ago(freshest)}</span>}
            {tab !== 'favorites' && (
              <button onClick={refresh} disabled={refreshing} title={`Refresh the ${tab} tab now`}
                className="inline-flex h-9 items-center gap-2 rounded-md border border-border px-3 text-xs font-medium text-text hover:border-accent/40 disabled:opacity-50">
                <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} /> {refreshing ? 'Refreshing…' : 'Refresh'}
              </button>
            )}
            <button onClick={() => setSettingsOpen(true)} title="Sources & schedules"
              className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-border text-muted hover:border-accent/40 hover:text-text">
              <Settings2 size={15} />
            </button>
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
        {job && (
          <RefreshProgress job={job} running={refreshing}
            onCancel={() => void cancelRefresh()}
            onRetry={() => void retryFailed()}
            onDismiss={() => setJob(null)} />
        )}
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
        {tab === 'home' && <HomeTab home={home} loading={loading} error={error} onRetry={load}
          sources={settings?.tab_sources?.home ?? []} />}
        {tab === 'trending' && <TrendingTab reloadKey={reloadKey} />}
        {tab === 'feed' && <FeedTab reloadKey={reloadKey} />}
        {tab === 'favorites' && <FavoritesTab />}
      </main>

      {settings && (
        <SourcesSettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)}
          settings={settings}
          onSaved={patch => setSettings(current => current ? { ...current, ...patch } : current)} />
      )}
    </div>
  )
}

/** Sources & schedules (plan §4/§7 settings surface): per-source on/off toggles —
 *  honored by the refresh engine, a disabled source never enters a job — plus the
 *  per-tab Daily/Weekly/Monthly schedule. Already-collected items always stay. */
function SourcesSettingsModal({ open, onClose, settings, onSaved }: {
  open: boolean; onClose: () => void; settings: NewsV2Settings
  onSaved: (patch: { enabled_sources: string[]; schedules: Record<string, string> }) => void
}) {
  const { toast } = useToast()
  const [enabled, setEnabled] = useState<Record<string, boolean>>({})
  const [schedules, setSchedules] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    if (!open) return
    const allOn = settings.enabled_sources.length === 0
    setEnabled(Object.fromEntries(settings.known_sources.map(name =>
      [name, allOn || settings.enabled_sources.includes(name)])))
    setSchedules({ ...settings.schedules })
  }, [open, settings])

  const tabsUsing = (source: string) =>
    Object.entries(settings.tab_sources).filter(([, names]) => names.includes(source)).map(([t]) => t)

  const save = async () => {
    setSaving(true)
    try {
      const on = settings.known_sources.filter(name => enabled[name])
      // every source on → store the default "all" ([]) so future sources join automatically
      const enabled_sources = on.length === settings.known_sources.length ? [] : on
      const result = await patchNewsV2Settings({ enabled_sources, schedules })
      onSaved({ enabled_sources: result.enabled_sources, schedules: result.schedules })
      toast({ kind: 'success', title: 'Sources updated' })
      onClose()
    } catch (err) {
      toast({ kind: 'error', title: 'Settings not saved', detail: err instanceof Error ? err.message : String(err) })
    } finally { setSaving(false) }
  }

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-50 flex items-start justify-center bg-background/85 p-4 backdrop-blur-sm sm:p-8"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.section role="dialog" aria-modal="true" onClick={event => event.stopPropagation()}
            initial={{ opacity: 0, y: 14, scale: 0.99 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 10, scale: 0.99 }}
            transition={{ duration: 0.16 }}
            className="mt-6 w-full max-w-lg overflow-hidden rounded-lg border border-border bg-surface shadow-2xl">
            <header className="flex items-center justify-between border-b border-border px-5 py-4">
              <div><h2 className="font-semibold text-text">Sources & schedules</h2>
                <p className="mt-0.5 text-xs text-muted">A disabled source is skipped by every future refresh — collected items stay.</p></div>
              <button onClick={onClose} title="Close" className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted hover:bg-overlay/10 hover:text-text"><X size={17} /></button>
            </header>
            <div className="max-h-[60vh] overflow-y-auto px-5 py-4">
              <h3 className="text-[10px] font-semibold uppercase tracking-wide text-muted">Connected sources</h3>
              <div className="mt-2 space-y-2">
                {settings.known_sources.map(name => (
                  <div key={name} className="flex items-center gap-3 rounded-md border border-border bg-background/40 px-3 py-2.5">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border bg-background">
                      <SourceLogo name={name} size={14} variant="inline" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium text-text">{name}</div>
                      <div className="text-[11px] text-muted">feeds: {tabsUsing(name).join(', ') || '—'}</div>
                    </div>
                    <button onClick={() => setEnabled(current => ({ ...current, [name]: !current[name] }))}
                      role="switch" aria-checked={enabled[name] ?? false} title={enabled[name] ? 'On — click to disable' : 'Off — click to enable'}
                      className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${enabled[name] ? 'bg-accent' : 'bg-overlay/25'}`}>
                      <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-background shadow transition-all ${enabled[name] ? 'left-[18px]' : 'left-0.5'}`} />
                    </button>
                  </div>
                ))}
              </div>
              <h3 className="mt-5 text-[10px] font-semibold uppercase tracking-wide text-muted">Refresh schedules</h3>
              <div className="mt-2 space-y-2">
                {Object.keys(schedules).map(tabName => (
                  <div key={tabName} className="flex items-center justify-between gap-3 rounded-md border border-border bg-background/40 px-3 py-2">
                    <span className="text-sm capitalize text-text">{tabName}</span>
                    <select value={schedules[tabName]} onChange={event => setSchedules(current => ({ ...current, [tabName]: event.target.value }))}
                      className="h-8 rounded-md border border-border bg-background px-2 text-xs capitalize text-text outline-none focus:border-accent">
                      {settings.schedule_options.map(option => <option key={option} value={option}>{option}</option>)}
                    </select>
                  </div>
                ))}
              </div>
            </div>
            <footer className="flex items-center justify-end gap-2 border-t border-border px-5 py-3">
              <button onClick={onClose} disabled={saving}
                className="inline-flex h-8 items-center rounded-md border border-border px-3 text-xs text-text disabled:opacity-50">Cancel</button>
              <button onClick={() => void save()} disabled={saving}
                className="inline-flex h-8 items-center gap-2 rounded-md bg-accent px-4 text-xs font-semibold text-background disabled:opacity-50">
                {saving ? <Loader2 size={12} className="animate-spin" /> : null} Save
              </button>
            </footer>
          </motion.section>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  )
}

/** Live refresh progress (plan §7: job/source/stage/progress) — renders the durable
 *  job row's per-source checkpoints: bar + one chip per source. Partial/failed stays
 *  visible with Retry failed (only failed sources re-run) instead of vanishing. */
function RefreshProgress({ job, running, onCancel, onRetry, onDismiss }: {
  job: NewsV2RefreshJob; running: boolean
  onCancel: () => void; onRetry: () => void; onDismiss: () => void
}) {
  const checkpoints = Object.entries(job.checkpoints)
  const done = checkpoints.filter(([, cp]) => cp.state === 'ok').length
  const failed = checkpoints.filter(([, cp]) => cp.state === 'failed')
  const total = Math.max(1, checkpoints.length)
  const inFlight = running
    ? checkpoints.find(([, cp]) => cp.state !== 'ok' && cp.state !== 'failed')?.[0]
    : undefined
  const pct = Math.round(((done + failed.length) / total) * 100)   // processed = ok + failed
  const label = running
    ? `Refreshing ${job.tab} — ${done}/${total} sources done`
    : job.state === 'partial'
      ? `Refresh finished — ${failed.length} source${failed.length === 1 ? '' : 's'} failed`
      : job.state === 'failed' ? 'Refresh failed — every source errored' : `Refresh ${job.state}`
  return (
    <div className="border-t border-border bg-surface/70 px-4 py-2 sm:px-6">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-3 gap-y-2">
        <span className="inline-flex items-center gap-2 text-[11px] font-medium text-text">
          {running ? <Loader2 size={13} className="animate-spin text-accent" />
            : failed.length ? <AlertTriangle size={13} className="text-warning" />
              : <Check size={13} className="text-success" />}
          {label}
        </span>
        <div className="h-1.5 w-36 overflow-hidden rounded-full bg-background/70">
          <div className={`h-full rounded-full transition-all duration-500 ${failed.length && !running ? 'bg-warning' : 'bg-accent'}`}
            style={{ width: `${Math.max(4, pct)}%` }} />
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {checkpoints.map(([source, cp]) => (
            <span key={source} title={cp.state === 'failed' ? (cp.error ?? 'failed') : cp.state ?? 'queued'}
              className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] ${
                cp.state === 'ok' ? 'border-success/40 bg-success/10 text-success'
                  : cp.state === 'failed' ? 'border-danger/40 bg-danger/10 text-danger'
                    : source === inFlight ? 'border-accent/40 bg-accent/10 text-accent'
                      : 'border-border text-muted'}`}>
              {cp.state === 'ok' ? <Check size={10} />
                : cp.state === 'failed' ? <X size={10} />
                  : source === inFlight ? <Loader2 size={10} className="animate-spin" />
                    : <CircleDashed size={10} />}
              {source}
            </span>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-1.5">
          {running ? (
            <button onClick={onCancel}
              className="inline-flex h-7 items-center gap-1.5 rounded-md border border-border px-2.5 text-[11px] text-muted hover:text-danger">
              <Ban size={11} /> Cancel
            </button>
          ) : (
            <>
              {failed.length > 0 && (
                <button onClick={onRetry}
                  className="inline-flex h-7 items-center gap-1.5 rounded-md border border-accent/40 bg-accent/10 px-2.5 text-[11px] font-medium text-accent hover:bg-accent/20">
                  <RefreshCw size={11} /> Retry failed
                </button>
              )}
              <button onClick={onDismiss} title="Dismiss"
                className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted hover:text-text">
                <X size={13} />
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

/** One category's Top-5 leaderboard card — mini table with relative benchmark bars,
 *  sources attributed in the header. Purely data-driven per category. */
function LeaderboardCard({ board }: { board: NewsV2Leaderboard }) {
  const top = board.entries[0]?.score || 100
  return (
    <section className="overflow-hidden rounded-lg border border-border bg-surface/50">
      <header className="flex h-10 items-center gap-2 border-b border-border px-3.5">
        <Trophy size={12} className="text-accent" />
        <h3 className="text-xs font-semibold capitalize text-text">{board.category}</h3>
        <span className="ml-auto"><SourceIconGroup sources={board.sources} size={16} /></span>
      </header>
      <div className="divide-y divide-border/50">
        {board.entries.map((entry, index) => {
          const tone = index === 0
            ? { row: 'bg-accent/[0.05]', badge: 'bg-accent text-background', bar: 'bg-accent' }
            : index === 1
              ? { row: '', badge: 'border border-accent/50 text-accent', bar: 'bg-accent/70' }
              : index === 2
                ? { row: '', badge: 'border border-accent/25 text-accent/80', bar: 'bg-accent/50' }
                : { row: '', badge: 'border border-border text-muted', bar: 'bg-overlay/30' }
          return (
            <div key={entry.model_id} title={`${entry.metrics} metrics · observed ${localTime(entry.observed_at)}`}
              className={`flex items-center gap-2.5 px-3.5 py-2 ${tone.row}`}>
              <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold ${tone.badge}`}>{index + 1}</span>
              <LlmLogo model={entry.model_id} size={11} className="h-5 w-5 border border-border bg-background" />
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs font-medium text-text">{entry.model_id}</div>
                <div className="mt-1 h-1 w-full max-w-[180px] overflow-hidden rounded-full bg-background/70">
                  <div className={`h-full rounded-full ${tone.bar}`}
                    style={{ width: `${Math.max(5, Math.round((entry.score / Math.max(1, top)) * 100))}%` }} />
                </div>
              </div>
              <span className="shrink-0 font-mono text-xs font-semibold text-text">{entry.score.toFixed(1)}</span>
            </div>
          )
        })}
      </div>
    </section>
  )
}

// ── Home (N08): Model Strength Top 10 + Latest Releases, always sourced + timed ──────
function HomeTab({ home, loading, error, onRetry, sources }: {
  home: NewsV2Home | null; loading: boolean; error: string | null; onRetry: () => void
  sources: string[]
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
            <div className="flex items-center gap-2.5">
              <SourceIconGroup sources={sources} />
              <button onClick={() => setExplorerOpen(true)}
                className="inline-flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-[11px] text-muted hover:text-accent">
                <Maximize2 size={11} /> Explore
              </button>
            </div>
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
          <header className="flex h-11 items-center gap-2 border-b border-border px-4"><Rss size={14} className="text-accent" /><h2 className="text-xs font-semibold text-text">Latest Releases</h2><span className="ml-auto"><SourceIconGroup sources={sources} /></span></header>
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
        <div className="mt-0.5 text-[11px] text-muted" title={localTime(release.released_at ?? release.observed_at)}>
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

// ── Full-screen Model Explorer (N08, redesigned): category leaderboard cards ─────────
// Overview = one Top-5 card per evidence category (data-driven — future benchmark
// categories like coding/image/video become new cards automatically). Searching
// flips to the detailed per-model evidence tables.
function ModelExplorerModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [q, setQ] = useState('')
  const [detail, setDetail] = useState(false)          // false → leaderboard overview
  const [boards, setBoards] = useState<Awaited<ReturnType<typeof getNewsV2ModelLeaderboards>>['categories']>([])
  const [category, setCategory] = useState('')
  const [models, setModels] = useState<{ model_id: string; metrics: NewsV2ModelMetric[] }[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setDetail(false); setQ(''); setCategory('')
    setBusy(true)
    void getNewsV2ModelLeaderboards()
      .then(res => { setBoards(res.categories); setFailed(null) })
      .catch(err => setFailed(err instanceof Error ? err.message : String(err)))
      .finally(() => setBusy(false))
  }, [open])

  const search = useCallback(async (reset: boolean, cur?: string | null) => {
    setDetail(true)
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
                <input value={q} onChange={event => setQ(event.target.value)} placeholder="Search by model id — opens detailed evidence"
                  onKeyDown={event => { if (event.key === 'Enter') void search(true) }}
                  className="h-9 w-full rounded-md border border-border bg-background pl-8 pr-3 text-sm text-text outline-none focus:border-accent" />
              </div>
              <select value={category} onChange={event => setCategory(event.target.value)}
                className="h-9 rounded-md border border-border bg-background px-2 text-xs capitalize text-text outline-none focus:border-accent">
                <option value="">All categories</option>
                {boards.map(board => <option key={board.category} value={board.category}>{board.category}</option>)}
              </select>
              <button onClick={() => void search(true)} disabled={busy}
                className="inline-flex h-9 items-center gap-2 rounded-md bg-accent px-3 text-xs font-semibold text-background disabled:opacity-50">
                {busy ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />} Search
              </button>
              {detail && (
                <button onClick={() => { setDetail(false); setQ('') }}
                  className="inline-flex h-9 items-center rounded-md border border-border px-3 text-xs text-text hover:border-accent/40">
                  ← Overview
                </button>
              )}
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
              {failed ? (
                <div className="flex items-center gap-2 rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger"><AlertTriangle size={13} /> {failed}</div>
              ) : !detail ? (
                busy && boards.length === 0 ? (
                  <div className="grid gap-4 sm:grid-cols-2">{[0, 1].map(i => (
                    <div key={i} className="h-56 animate-pulse rounded-lg border border-border bg-surface/40" />))}
                  </div>
                ) : boards.length === 0 ? (
                  <p className="py-12 text-center text-xs text-muted">No model evidence yet — run a Home refresh first.</p>
                ) : (
                  <div className="grid gap-4 sm:grid-cols-2">
                    {boards.map(board => <LeaderboardCard key={board.category} board={board} />)}
                  </div>
                )
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
                                <td className="px-3 py-1.5 text-muted" title={localTime(metric.observed_at)}>{ago(metric.observed_at)}</td>
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

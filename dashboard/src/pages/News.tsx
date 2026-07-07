import { useEffect, useState, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Newspaper, Trophy, Wrench, MessageCircle, RefreshCw, Sparkles, Settings2,
  ExternalLink, Eye, Flame, Clock, Filter, X, ChevronDown, Loader2, Zap, Globe,
} from 'lucide-react'
import {
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from 'recharts'
import {
  type ExploreItem, type ExploreModel, type ExploreConfig, type ExploreSource, type ExploreStatus,
  getExploreStatus, getExploreNews, getExploreModels, getExploreTools, getExploreSocial,
  refreshExplore, getExploreConfig, saveExploreConfig, setExploreSource, exploreDigest,
} from '../api'
import { useToast } from '../context/ToastProvider'
import LlmLogo, { brandForModel } from '../components/LlmLogo'
import RadarChart from '../components/RadarChart'

type Tab = 'models' | 'tools' | 'social'

export default function News() {
  const { toast } = useToast()
  const [tab, setTab] = useState<Tab>('models')
  const [status, setStatus] = useState<ExploreStatus | null>(null)
  const [news, setNews] = useState<ExploreItem[]>([])
  const [models, setModels] = useState<ExploreModel[]>([])
  const [tools, setTools] = useState<ExploreItem[]>([])
  const [social, setSocial] = useState<ExploreItem[]>([])
  const [cfg, setCfg] = useState<ExploreConfig | null>(null)
  const [sources, setSources] = useState<ExploreSource[]>([])
  const [refreshing, setRefreshing] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [showConfig, setShowConfig] = useState(false)
  const [digest, setDigest] = useState<string | null>(null)
  const [digesting, setDigesting] = useState(false)

  const load = async () => {
    // One batched Promise.all so the whole page renders at once (no wave-by-wave
    // pop-in). Keeps existing data on refresh — only the very first load gates UI.
    try {
      const [s, n, m, t, so, c] = await Promise.all([
        getExploreStatus(), getExploreNews(12), getExploreModels(60),
        getExploreTools(40), getExploreSocial(40), getExploreConfig().catch(() => null),
      ])
      setStatus(s); setNews(n.items); setModels(m.models)
      setTools(t.items); setSocial(so.items)
      if (c) { setCfg(c.config); setSources(c.sources) }
    } catch (e) { toast({ kind: 'error', title: 'Load failed', detail: (e as Error).message }) }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const refresh = async (pillar: 'models' | 'tools' | 'social' | 'news' | 'all') => {
    setRefreshing(pillar)
    try {
      const r = await refreshExplore(pillar)
      setStatus(r.status)
      // Re-fetch the touched pillars in parallel — keep stale data until all land,
      // so nothing blanks out mid-refresh.
      const tasks: Promise<unknown>[] = []
      if (pillar === 'all' || pillar === 'news') tasks.push(getExploreNews(12).then(x => setNews(x.items)))
      if (pillar === 'all' || pillar === 'models') tasks.push(getExploreModels(60).then(x => setModels(x.models)))
      if (pillar === 'all' || pillar === 'tools') tasks.push(getExploreTools(40).then(x => setTools(x.items)))
      if (pillar === 'all' || pillar === 'social') tasks.push(getExploreSocial(40).then(x => setSocial(x.items)))
      await Promise.all(tasks)
      toast({ kind: 'success', title: 'Refreshed', detail: pillar === 'all' ? 'All pillars' : pillar })
    } catch (e) { toast({ kind: 'error', title: 'Refresh failed', detail: (e as Error).message }) }
    finally { setRefreshing(null) }
  }

  const runDigest = async () => {
    setDigesting(true)
    try { setDigest((await exploreDigest(1)).text) }
    catch (e) { toast({ kind: 'error', title: 'Digest failed', detail: (e as Error).message }) }
    finally { setDigesting(false) }
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
        {/* Header */}
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-accent/30 bg-accent/10 text-accent"><Newspaper size={18} /></div>
            <div>
              <h1 className="text-base font-bold text-heading">Explore · News</h1>
              <p className="text-[11px] text-muted">TOBI-conducted AI news, models, tools & social — fetch → dedupe → summarize → rank.</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <BudgetChip status={status} />
            <button onClick={runDigest} disabled={digesting}
              className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs text-muted hover:border-accent/40 hover:text-accent disabled:opacity-50">
              {digesting ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />} Digest
            </button>
            <div className="flex items-center rounded-lg border border-border">
              <button onClick={() => refresh('all')} disabled={!!refreshing}
                className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-muted hover:text-accent disabled:opacity-50">
                <RefreshCw size={13} className={refreshing === 'all' ? 'animate-spin' : ''} /> All
              </button>
              <button onClick={() => refresh(tab === 'models' ? 'models' : tab)} disabled={!!refreshing}
                className="flex items-center gap-1.5 border-l border-border px-2.5 py-1.5 text-xs text-muted hover:text-accent disabled:opacity-50">
                <RefreshCw size={13} className={refreshing && refreshing !== 'all' ? 'animate-spin' : ''} /> This tab
              </button>
            </div>
            <button onClick={() => setShowConfig(true)} className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs text-muted hover:border-accent/40 hover:text-accent">
              <Settings2 size={13} />
            </button>
          </div>
        </div>

        {/* Headlines rail */}
        {news.length > 0 && (
          <div className="mb-5">
            <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-widest text-muted">
              <Globe size={12} className="text-accent" /> Top AI headlines
            </div>
            <div className="flex gap-2 overflow-x-auto pb-2">
              {news.map((n, i) => <HeadlineCard key={n.ext_id + i} item={n} />)}
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="mb-4 flex items-center gap-1 rounded-lg border border-border bg-surface/50 p-1">
          {([['models', 'Models', Trophy], ['tools', 'Tools', Wrench], ['social', 'Social', MessageCircle]] as const).map(([id, label, Icon]) => (
            <button key={id} onClick={() => setTab(id)}
              className={`relative flex flex-1 items-center justify-center gap-1.5 rounded-md py-1.5 text-xs font-medium transition-colors ${tab === id ? 'text-accent' : 'text-muted hover:text-text'}`}>
              {tab === id && <motion.span layoutId="newsTab" className="absolute inset-0 rounded-md bg-accent/15 ring-1 ring-accent/20" transition={{ type: 'spring', stiffness: 380, damping: 30 }} />}
              <Icon size={13} className="relative z-10" /><span className="relative z-10">{label}</span>
            </button>
          ))}
        </div>

        {/* Tab content — single loading gate so nothing flashes empty before data lands */}
        {loading ? <TabLoader /> : (
          <>
            {tab === 'models' && <ModelsTab models={models} />}
            {tab === 'tools' && <ToolsTab items={tools} muted={cfg?.muted_categories || []} />}
            {tab === 'social' && <SocialTab items={social} />}
          </>
        )}
      </div>

      {/* Config drawer */}
      <AnimatePresence>
        {showConfig && cfg && (
          <ConfigDrawer cfg={cfg} sources={sources} onClose={() => setShowConfig(false)}
            onChanged={async (c, s) => { setCfg(c); if (s) setSources(s) }} />
        )}
      </AnimatePresence>

      {/* Digest modal */}
      <AnimatePresence>
        {digest !== null && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm" onClick={() => setDigest(null)}>
            <motion.div initial={{ scale: 0.96, y: 10 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.96, y: 10 }}
              onClick={e => e.stopPropagation()}
              className="max-h-[80vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-border bg-surface p-5 shadow-2xl">
              <div className="mb-3 flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm font-bold text-heading"><Sparkles size={16} className="text-accent" /> TOBI's daily brief</div>
                <button onClick={() => setDigest(null)} className="text-muted hover:text-text"><X size={16} /></button>
              </div>
              <div className="whitespace-pre-wrap text-[13px] leading-relaxed text-text">{digest || 'Nothing to summarize yet — refresh first.'}</div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Headlines rail card ──────────────────────────────────────────────────────
function HeadlineCard({ item }: { item: ExploreItem }) {
  return (
    <a href={item.url || '#'} target="_blank" rel="noreferrer"
      className="block w-64 shrink-0 rounded-lg border border-border bg-surface p-2.5 transition-colors hover:border-accent/40">
      <div className="mb-1 flex items-center gap-1.5 text-[10px] text-muted">
        <span className="rounded bg-bg/60 px-1 py-0.5">{item.source_name}</span>
        {item.freshness && <FreshnessBadge f={item.freshness} />}
      </div>
      <div className="line-clamp-2 text-xs font-medium text-text">{item.title}</div>
      {item.summary && <div className="mt-1 line-clamp-2 text-[11px] text-muted">{item.summary}</div>}
    </a>
  )
}

// ── Models tab ───────────────────────────────────────────────────────────────
type SortKey = 'composite' | 'intelligence' | 'popularity' | 'price_in' | 'context'
function ModelsTab({ models }: { models: ExploreModel[] }) {
  const [sort, setSort] = useState<SortKey>('composite')
  const [compare, setCompare] = useState<string[]>([])
  const sorted = useMemo(() => {
    const arr = [...models]
    arr.sort((a, b) => {
      const av = a[sort]; const bv = b[sort]
      if (av == null) return 1; if (bv == null) return -1
      return sort === 'price_in' ? av - bv : bv - av
    })
    return arr
  }, [models, sort])

  const scatter = useMemo(() => models.map(m => ({
    x: m.price_in ?? 0, y: m.intelligence ?? 0, z: m.popularity ?? 1, label: m.model_id, provider: m.provider,
  })).filter(d => d.x !== null), [models])

  const radarSeries = compare
    .map(id => models.find(m => m.model_id === id)).filter(Boolean)
    .map((m, i) => ({
      label: m!.model_id.split('/').pop()!,
      color: ['#10A37F', '#D97757', '#4285F4'][i % 3],
      values: [
        Math.round(m!.intelligence ?? 0),
        Math.round(m!.elo ?? 50),
        Math.round(m!.popularity ?? 0),
        m!.context ? Math.min(100, Math.round(m!.context / 4000)) : 0,
        m!.price_in ? Math.max(0, Math.round(100 - m!.price_in)) : 50,
      ],
    }))

  const toggleCompare = (id: string) =>
    setCompare(c => c.includes(id) ? c.filter(x => x !== id) : c.length >= 3 ? c : [...c, id])

  if (!models.length) return <Empty kind="models" />
  return (
    <div className="space-y-4">
      {/* scatter */}
      {scatter.length > 1 && (
        <div className="rounded-xl border border-border bg-surface/40 p-3">
          <div className="mb-2 text-[11px] font-medium text-muted">Price (in $/M tok) × Intelligence · bubble = popularity</div>
          <ResponsiveContainer width="100%" height={220}>
            <ScatterChart margin={{ top: 4, right: 12, bottom: 16, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--border))" opacity={0.4} />
              <XAxis type="number" dataKey="x" name="Price" tick={{ fill: 'rgb(var(--muted))', fontSize: 10 }} stroke="rgb(var(--border))" />
              <YAxis type="number" dataKey="y" name="Intel" tick={{ fill: 'rgb(var(--muted))', fontSize: 10 }} stroke="rgb(var(--border))" />
              <ZAxis type="number" dataKey="z" range={[40, 360]} />
              <Tooltip cursor={{ strokeDasharray: '3 3' }} contentStyle={{ background: 'rgb(var(--surface))', border: '1px solid rgb(var(--border))', borderRadius: 8, fontSize: 11 }}
                formatter={(_v, _n, p: any) => [`${p.payload.label}`, 'Model']} labelFormatter={() => ''} />
              <Scatter data={scatter} fill="rgb(var(--accent))" fillOpacity={0.55} />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* compare radar */}
      {radarSeries.length > 0 && (
        <div className="rounded-xl border border-border bg-surface/40 p-4">
          <div className="mb-2 flex items-center justify-between">
            <div className="text-[11px] font-medium text-muted">Compare ({compare.length}/3)</div>
            <button onClick={() => setCompare([])} className="text-[11px] text-muted hover:text-text">Clear</button>
          </div>
          <div className="flex flex-wrap items-center justify-center gap-4">
            <RadarChart axes={['Intel', 'Elo', 'Popular', 'Context', 'Value']} series={radarSeries} size={260} />
          </div>
        </div>
      )}

      {/* leaderboard */}
      <div className="overflow-hidden rounded-xl border border-border">
        <table className="w-full text-left text-xs">
          <thead className="bg-surface/60 text-[10px] uppercase tracking-wide text-muted">
            <tr>
              <th className="px-2 py-2">#</th>
              <th className="px-2 py-2">Model</th>
              <Th k="intelligence" sort={sort} onSort={setSort}>Intel</Th>
              <Th k="price_in" sort={sort} onSort={setSort}>$/M in</Th>
              <Th k="context" sort={sort} onSort={setSort}>Ctx</Th>
              <Th k="popularity" sort={sort} onSort={setSort}>Popular</Th>
              <Th k="composite" sort={sort} onSort={setSort}>Score</Th>
            </tr>
          </thead>
          <tbody>
            {sorted.slice(0, 50).map((m, i) => {
              const selected = compare.includes(m.model_id)
              return (
                <tr key={m.model_id} onClick={() => toggleCompare(m.model_id)}
                  className={`cursor-pointer border-t border-border/50 transition-colors ${selected ? 'bg-accent/10' : 'hover:bg-bg/40'}`}>
                  <td className="px-2 py-1.5 text-muted">{i + 1}</td>
                  <td className="px-2 py-1.5">
                    <div className="flex items-center gap-1.5">
                      <span className="text-heading" title={m.model_id}>{m.model_id.split('/').pop()}</span>
                      {selected && <span className="text-[9px] text-accent">●</span>}
                    </div>
                  </td>
                  <td className="px-2 py-1.5 tabular-nums text-text">{m.intelligence?.toFixed(0) ?? '—'}</td>
                  <td className="px-2 py-1.5 tabular-nums text-text">{m.price_in != null ? `$${m.price_in.toFixed(1)}` : '—'}</td>
                  <td className="px-2 py-1.5 tabular-nums text-text">{m.context ? `${Math.round(m.context / 1000)}k` : '—'}</td>
                  <td className="px-2 py-1.5 tabular-nums text-text">{m.popularity?.toFixed(0) ?? '—'}</td>
                  <td className="px-2 py-1.5">
                    <div className="flex items-center gap-1.5">
                      <div className="h-1.5 w-14 overflow-hidden rounded-full bg-bg/60">
                        <div className="h-full rounded-full bg-accent" style={{ width: `${Math.min(100, m.composite)}%` }} />
                      </div>
                      <span className="tabular-nums text-text">{m.composite.toFixed(0)}</span>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Th({ k, sort, onSort, children }: { k: SortKey; sort: SortKey; onSort: (k: SortKey) => void; children: React.ReactNode }) {
  return (
    <th className="cursor-pointer px-2 py-2 hover:text-text" onClick={() => onSort(k)}>
      <span className="inline-flex items-center gap-0.5">{children}
        <ChevronDown size={9} className={sort === k ? 'text-accent' : 'opacity-30'} />
      </span>
    </th>
  )
}

// ── Tools tab ────────────────────────────────────────────────────────────────
function ToolsTab({ items, muted }: { items: ExploreItem[]; muted: string[] }) {
  const cats = useMemo(() => Array.from(new Set(items.map(i => i.source_name))).sort(), [items])
  const [filter, setFilter] = useState<string | null>(null)
  const shown = items.filter(i => !filter || i.source_name === filter)
  if (!items.length) return <Empty kind="tools" />
  return (
    <div>
      <div className="mb-2.5 flex flex-wrap items-center gap-1.5">
        <span className="flex items-center gap-1 text-[11px] text-muted"><Filter size={11} /> Source:</span>
        <button onClick={() => setFilter(null)} className={chipCls(!filter)}>All</button>
        {cats.map(c => <button key={c} onClick={() => setFilter(c)} className={chipCls(filter === c)}>{c}</button>)}
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {shown.map((it, i) => <ToolCard key={it.ext_id + i} item={it} muted={muted} />)}
      </div>
    </div>
  )
}

function ToolCard({ item, muted }: { item: ExploreItem; muted: string[] }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-xl border border-border bg-surface p-3">
      <div className="mb-1 flex items-center gap-1.5">
        <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[10px] font-medium text-accent">{item.source_name}</span>
        {item.freshness && <FreshnessBadge f={item.freshness} />}
        {item.engagement > 0 && <span className="ml-auto flex items-center gap-0.5 text-[10px] text-muted"><Flame size={10} /> {item.engagement.toLocaleString()}</span>}
      </div>
      <div className="text-sm font-semibold text-heading">{item.title}</div>
      {item.summary && (
        <p className={`mt-1 text-[12px] leading-snug text-muted ${open ? '' : 'line-clamp-2'}`}>{item.summary}</p>
      )}
      <div className="mt-2 flex items-center gap-1.5">
        {item.url && <a href={item.url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-[11px] text-accent hover:underline">open <ExternalLink size={10} /></a>}
        {item.summary && <button onClick={() => setOpen(o => !o)} className="text-[11px] text-muted hover:text-text">{open ? 'less' : 'more'}</button>}
      </div>
    </div>
  )
}

// ── Social tab ───────────────────────────────────────────────────────────────
function SocialTab({ items }: { items: ExploreItem[] }) {
  if (!items.length) return <Empty kind="social" />
  return (
    <div className="space-y-1.5">
      {items.map((it, i) => <SocialRow key={it.ext_id + i} item={it} rank={i + 1} />)}
    </div>
  )
}

function SocialRow({ item, rank }: { item: ExploreItem; rank: number }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-lg border border-border bg-surface p-2.5">
      <div className="flex items-start gap-2.5">
        <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded bg-accent/10 text-[10px] font-bold text-accent">{rank}</span>
        <div className="min-w-0 flex-1">
          <div className="mb-0.5 flex flex-wrap items-center gap-1.5">
            <span className="rounded bg-bg/60 px-1 py-0.5 text-[10px] text-muted">{item.source_name}</span>
            {item.freshness && <FreshnessBadge f={item.freshness} />}
            {item.engagement > 0 && <span className="flex items-center gap-0.5 text-[10px] text-muted"><Flame size={10} /> {item.engagement.toLocaleString()}</span>}
            {item.published_at && <span className="flex items-center gap-0.5 text-[10px] text-muted"><Clock size={10} /> {timeAgo(item.published_at)}</span>}
          </div>
          <div className="text-[13px] font-medium text-heading">{item.title}</div>
          {item.summary && open && <p className="mt-1 text-[12px] leading-snug text-muted">{item.summary}</p>}
          <div className="mt-1 flex items-center gap-2">
            {item.url && <a href={item.url} target="_blank" rel="noreferrer" className="text-[11px] text-accent hover:underline">source</a>}
            {item.summary && <button onClick={() => setOpen(o => !o)} className="text-[11px] text-muted hover:text-text">{open ? 'less' : 'summary'}</button>}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Config drawer ────────────────────────────────────────────────────────────
function ConfigDrawer({ cfg, sources, onClose, onChanged }: {
  cfg: ExploreConfig; sources: ExploreSource[]; onClose: () => void
  onChanged: (cfg: ExploreConfig, sources?: ExploreSource[]) => void
}) {
  const { toast } = useToast()
  const [local, setLocal] = useState<ExploreConfig>(cfg)
  const [saving, setSaving] = useState(false)
  const patch = (p: Partial<ExploreConfig>) => setLocal(c => ({ ...c, ...p }))

  const save = async (updates: Partial<ExploreConfig>) => {
    setSaving(true)
    try { const r = await saveExploreConfig(updates); setLocal(r.config); onChanged(r.config, r.sources); toast({ kind: 'success', title: 'Saved' }) }
    catch (e) { toast({ kind: 'error', title: 'Save failed', detail: (e as Error).message }) }
    finally { setSaving(false) }
  }
  const toggleSrc = async (s: ExploreSource, enabled: boolean) => {
    try { const r = await setExploreSource(s.name, enabled); onChanged(local, r.sources); toast({ kind: 'info', title: `${s.name} ${enabled ? 'on' : 'off'}` }) }
    catch (e) { toast({ kind: 'error', title: 'Failed' }) }
  }

  return (
    <>
      <div className="fixed inset-0 z-[90] bg-black/60" onClick={onClose} />
      <motion.div initial={{ x: 360 }} animate={{ x: 0 }} exit={{ x: 360 }} transition={{ type: 'spring', stiffness: 360, damping: 34 }}
        className="fixed right-0 top-0 z-[91] flex h-full w-96 max-w-[90vw] flex-col border-l border-border bg-surface shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-bold text-heading"><Settings2 size={15} /> Explore config</div>
          <button onClick={onClose} className="text-muted hover:text-text"><X size={16} /></button>
        </div>
        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-4">
          {/* sources */}
          <Section title="Sources">
            {sources.map(s => (
              <div key={s.name} className="flex items-center justify-between py-1 text-xs">
                <div className="min-w-0">
                  <div className="font-medium text-text">{s.name} <span className="text-muted">· {s.pillar}</span></div>
                  <div className="text-[10px]">
                    {s.status === 'ready'
                      ? <span className="text-success">ready</span>
                      : s.status === 'needs_key'
                        ? <a href="/integrations" className="text-accent hover:underline">needs key → add in Integrations</a>
                        : s.status === 'opt_in_required'
                          ? <span className="text-warning">opt-in (enable X below)</span>
                          : <span className="text-muted">{s.status}</span>}
                  </div>
                </div>
                <button onClick={() => toggleSrc(s, !s.enabled)} disabled={s.status === 'opt_in_required'}
                  className={`relative h-4 w-7 shrink-0 rounded-full border transition-colors disabled:opacity-40 ${s.enabled ? 'border-accent/50 bg-accent/30' : 'border-border bg-bg'}`}>
                  <span className={`absolute top-0.5 h-2.5 w-2.5 rounded-full bg-text transition-all ${s.enabled ? 'left-[14px]' : 'left-0.5'}`} />
                </button>
              </div>
            ))}
          </Section>

          {/* ranking */}
          <Section title="Ranking">
            <label className="block">
              <div className="mb-1 flex justify-between text-[11px] text-muted"><span>Engagement</span><span>Recency</span></div>
              <input type="range" min={0} max={1} step={0.1} value={local.recency_vs_engagement}
                onChange={e => patch({ recency_vs_engagement: parseFloat(e.target.value) })}
                onMouseUp={() => save({ recency_vs_engagement: local.recency_vs_engagement })}
                className="w-full accent-accent" />
            </label>
            <label className="mt-2 block text-[11px] text-muted">Keyword include (boost)</label>
            <input value={(local.keyword_include || []).join(', ')} onChange={e => patch({ keyword_include: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })}
              onBlur={() => save({ keyword_include: local.keyword_include })}
              placeholder="agents, rag, vietnam" className={inputCls} />
            <label className="mt-2 block text-[11px] text-muted">Keyword exclude (mute)</label>
            <input value={(local.keyword_exclude || []).join(', ')} onChange={e => patch({ keyword_exclude: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })}
              onBlur={() => save({ keyword_exclude: local.keyword_exclude })}
              placeholder="crypto, spam" className={inputCls} />
            <label className="mt-2 block text-[11px] text-muted">Interest prompt (seed from Brain)</label>
            <textarea value={local.interest_prompt || ''} onChange={e => patch({ interest_prompt: e.target.value })}
              onBlur={() => save({ interest_prompt: local.interest_prompt })}
              rows={3} placeholder="I care about: local AI tools for Vietnamese service businesses, agent frameworks, cost optimization."
              className={inputCls} />
          </Section>

          {/* model composite weights */}
          <Section title="Model composite weights">
            {(['intelligence', 'elo', 'popularity'] as const).map(k => (
              <label key={k} className="mb-1.5 flex items-center gap-2 text-[11px] text-muted">
                <span className="w-20 capitalize">{k}</span>
                <input type="range" min={0} max={1} step={0.05} value={local.model_weights[k]}
                  onChange={e => patch({ model_weights: { ...local.model_weights, [k]: parseFloat(e.target.value) } })}
                  onMouseUp={() => save({ model_weights: local.model_weights })}
                  className="flex-1 accent-accent" />
                <span className="w-8 tabular-nums">{local.model_weights[k].toFixed(2)}</span>
              </label>
            ))}
          </Section>

          {/* X opt-in */}
          <Section title="X / Twitter (pay-per-use)">
            <label className="flex items-center justify-between py-1 text-xs">
              <span className="text-text">Enable X source</span>
              <button onClick={() => save({ x_enabled: !local.x_enabled })}
                className={`relative h-4 w-7 rounded-full border transition-colors ${local.x_enabled ? 'border-accent/50 bg-accent/30' : 'border-border bg-bg'}`}>
                <span className={`absolute top-0.5 h-2.5 w-2.5 rounded-full bg-text transition-all ${local.x_enabled ? 'left-[14px]' : 'left-0.5'}`} />
              </button>
            </label>
            <label className="mt-1 block text-[11px] text-muted">Spend cap (USD)</label>
            <input type="number" step="0.5" min="0" value={local.x_cap_usd || 0}
              onChange={e => patch({ x_cap_usd: parseFloat(e.target.value) || 0 })}
              onBlur={() => save({ x_cap_usd: local.x_cap_usd })}
              className={inputCls} />
          </Section>

          {/* budget */}
          <Section title="LLM budget (summarization)">
            <label className="block text-[11px] text-muted">Monthly cap (USD)</label>
            <input type="number" step="0.5" min="0" value={local.monthly_budget_usd || 5}
              onChange={e => patch({ monthly_budget_usd: parseFloat(e.target.value) || 0 })}
              onBlur={() => save({ monthly_budget_usd: local.monthly_budget_usd })}
              className={inputCls} />
          </Section>
        </div>
        <div className="border-t border-border p-3">
          <button onClick={() => save(local)} disabled={saving}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-accent/20 py-2 text-xs font-semibold text-accent hover:bg-accent/30 disabled:opacity-50">
            {saving ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />} Save all
          </button>
        </div>
      </motion.div>
    </>
  )
}

// ── shared bits ──────────────────────────────────────────────────────────────
function BudgetChip({ status }: { status: ExploreStatus | null }) {
  if (!status) return null
  const { spent_usd, cap_usd, ok } = status.budget
  return (
    <span className={`flex items-center gap-1 rounded-lg border px-2 py-1.5 text-[11px] ${ok ? 'border-border text-muted' : 'border-danger/40 text-danger'}`}
      title="LLM summarization spend this month">
      <Zap size={11} /> ${spent_usd.toFixed(2)}/${cap_usd.toFixed(0)}
    </span>
  )
}

function FreshnessBadge({ f }: { f: string }) {
  const cls = f === 'Hot' ? 'bg-danger/15 text-danger' : f === 'New' ? 'bg-success/15 text-success' : f === 'Cooling' ? 'bg-muted/15 text-muted' : 'bg-bg/40 text-muted'
  return <span className={`rounded px-1 py-0.5 text-[9px] font-medium ${cls}`}>{f}</span>
}

function Empty({ kind }: { kind: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-16 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-border bg-surface text-muted"><Newspaper size={22} /></div>
      <div className="text-sm font-semibold text-heading">No {kind} data yet</div>
      <p className="max-w-xs text-xs text-muted">Hit “All” or “This tab” refresh in the header to run the first scan. Free sources work without keys; key-gated sources activate when you add them in Integrations.</p>
    </div>
  )
}

function TabLoader() {
  // Skeleton placeholder shown during the initial load so the tab never flashes
  // an "empty" state before data arrives.
  return (
    <div className="space-y-2">
      {[0, 1, 2, 3, 4, 5].map(i => (
        <div key={i} className="flex items-center gap-3 rounded-lg border border-border bg-surface p-3">
          <div className="h-8 w-8 shrink-0 animate-pulse rounded-md bg-bg/60" />
          <div className="flex-1 space-y-1.5">
            <div className="h-3 w-2/3 animate-pulse rounded bg-bg/60" />
            <div className="h-2.5 w-1/3 animate-pulse rounded bg-bg/40" />
          </div>
          <div className="h-3 w-12 shrink-0 animate-pulse rounded bg-bg/40" />
        </div>
      ))}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <div className="mb-1.5 text-[10px] font-bold uppercase tracking-widest text-muted">{title}</div>
      <div>{children}</div>
    </section>
  )
}

function timeAgo(iso: string): string {
  try {
    const d = new Date(iso); const s = (Date.now() - d.getTime()) / 1000
    if (s < 3600) return `${Math.round(s / 60)}m`
    if (s < 86400) return `${Math.round(s / 3600)}h`
    return `${Math.round(s / 86400)}d`
  } catch { return '' }
}

const chipCls = (active: boolean) => `rounded-full px-2 py-0.5 text-[11px] transition-colors ${active ? 'bg-accent/15 text-accent' : 'bg-bg/40 text-muted hover:text-text'}`
const inputCls = 'mt-1 w-full rounded-md border border-border bg-bg px-2 py-1.5 text-xs text-text outline-none focus:border-accent/50'

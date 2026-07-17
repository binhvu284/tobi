import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Brain as BrainIcon, Search, Plus, Upload, Sparkles, Inbox, Filter,
  RefreshCw, ScrollText, X, AlertTriangle, Clock,
  FileText, MessagesSquare, Pencil, Wand2, CircleDot,
  CheckSquare, Square, Trash2, ListChecks, Loader2,
  ArrowDownUp, Sparkle, CalendarClock, TrendingUp, ArrowDownAZ, Check,
} from 'lucide-react'
import {
  type Memory, type MemoryCategory, type BrainStats,
  getBrainCategories, getBrainStats, getMemories, searchMemories,
  getNarrative, makeNarrative, runBrainSweep, deleteMemory,
} from '../api'
import { useToast } from '../context/ToastProvider'
import PageLoader from '../components/PageLoader'
import MemoryModal from '../components/brain/MemoryModal'
import BrainImportModal from '../components/brain/BrainImportModal'
import CleanDuplicatesModal from '../components/brain/CleanDuplicatesModal'
import ReviewInbox from '../components/brain/ReviewInbox'

export default function Brain() {
  const { toast } = useToast()
  const [categories, setCategories] = useState<MemoryCategory[]>([])
  const [stats, setStats] = useState<BrainStats | null>(null)
  const [memories, setMemories] = useState<Memory[]>([])
  const [loading, setLoading] = useState(true)

  const [activeCat, setActiveCat] = useState('all')
  const [query, setQuery] = useState('')
  const [semantic, setSemantic] = useState(false)
  const [showFilters, setShowFilters] = useState(false)
  const [source, setSource] = useState('all')
  const [staleOnly, setStaleOnly] = useState(false)
  const [sortBy, setSortBy] = useState('default')

  const [modal, setModal] = useState<Memory | 'new' | null>(null)
  const [showImport, setShowImport] = useState(false)
  const [showDupes, setShowDupes] = useState(false)
  const [showReview, setShowReview] = useState(false)
  const [narrative, setNarrative] = useState<string | null>(null)
  const [narrativeBusy, setNarrativeBusy] = useState(false)

  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [confirmDel, setConfirmDel] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const catMap = useMemo(() => Object.fromEntries(categories.map(c => [c.id, c])), [categories])

  const sorted = useMemo(() => {
    const arr = [...memories]
    switch (sortBy) {
      case 'latest':
        // Latest first — by the most recent of created_at / updated_at
        return arr.sort((a, b) => {
          const ta = Math.max(new Date(a.updated_at || 0).getTime(), new Date(a.created_at || 0).getTime())
          const tb = Math.max(new Date(b.updated_at || 0).getTime(), new Date(b.created_at || 0).getTime())
          return tb - ta
        })
      case 'confidence':
        // Confidence first — high to low, stale items pushed below non-stale at same level
        return arr.sort((a, b) => {
          if (a.stale !== b.stale) return a.stale ? 1 : -1
          return b.confidence - a.confidence
        })
      case 'az':
        // A-Z — alphabetical by content
        return arr.sort((a, b) => (a.content || '').localeCompare(b.content || ''))
      default:
        // Default — importance: non-stale first, then confidence, then recency
        return arr.sort((a, b) => {
          if (a.stale !== b.stale) return a.stale ? 1 : -1
          if (b.confidence !== a.confidence) return b.confidence - a.confidence
          return (b.created_at || '').localeCompare(a.created_at || '')
        })
    }
  }, [memories, sortBy])

  const reloadMeta = useCallback(() => {
    getBrainStats().then(setStats).catch(() => {})
  }, [])

  const reloadMemories = useCallback(async () => {
    try {
      if (semantic && query.trim()) {
        const { items } = await searchMemories(query.trim(), 30)
        setMemories(activeCat === 'all' ? items : items.filter(m => m.category === activeCat))
      } else {
        const { items } = await getMemories({
          category: activeCat, q: query || undefined, source,
          stale: staleOnly || undefined, status: 'active',
        })
        setMemories(items)
      }
    } catch { /* keep */ }
  }, [semantic, query, activeCat, source, staleOnly])

  useEffect(() => {
    Promise.all([getBrainCategories(), getBrainStats()])
      .then(([c, s]) => { setCategories(c.categories); setStats(s) })
      .catch(() => {})
      .finally(() => setLoading(false))
    getNarrative().then(n => setNarrative(n.content)).catch(() => {})
  }, [])

  useEffect(() => { reloadMemories() }, [reloadMemories])

  const afterChange = () => { reloadMemories(); reloadMeta() }

  const exitSelect = () => { setSelectMode(false); setSelected(new Set()); setConfirmDel(false) }
  const toggleSel = (id: number) => setSelected(s => {
    const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n
  })
  const selectAll = () => setSelected(new Set(memories.map(m => m.id)))
  const bulkDelete = async () => {
    setDeleting(true)
    try {
      await Promise.all([...selected].map(id => deleteMemory(id)))
      toast({ kind: 'success', title: 'Deleted', detail: `${selected.size} ${selected.size === 1 ? 'memory' : 'memories'} removed` })
      exitSelect(); afterChange()
    } catch (e) {
      toast({ kind: 'error', title: 'Delete failed', detail: (e as Error).message })
    } finally { setDeleting(false) }
  }

  const regenNarrative = async () => {
    setNarrativeBusy(true)
    try {
      const n = await makeNarrative()
      setNarrative(n.content)
      toast({ kind: 'success', title: 'Narrative updated' })
    } catch (e) {
      toast({ kind: 'error', title: 'Could not synthesize', detail: (e as Error).message })
    } finally { setNarrativeBusy(false) }
  }

  const [sweeping, setSweeping] = useState(false)
  const sweep = async () => {
    setSweeping(true)
    try {
      const res = await runBrainSweep()
      toast({ kind: 'info', title: 'Brain sweep', detail: res.processed ? `Processed ${res.processed} messages` : 'Nothing new' })
      afterChange()
    } catch (e) { toast({ kind: 'error', title: 'Sweep failed', detail: (e as Error).message }) }
    finally { setSweeping(false) }
  }

  if (loading) return <PageLoader preset="brain" />

  const sources = stats ? Object.keys(stats.by_source) : []

  return (
    <div className="space-y-4 p-5 sm:p-6">
      {/* Header + stats */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-purple/30 bg-purple/10 text-purple"><BrainIcon size={18} /></div>
          <div>
            <h1 className="text-lg font-bold text-heading">Brain</h1>
            <p className="text-[11px] text-muted">What TOBI knows about you · {stats?.total ?? 0} memories{stats && !stats.embeddings ? ' · keyword search' : ''}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link to="/brain" className="flex items-center gap-1.5 rounded-lg border border-purple/40 bg-purple/10 px-2.5 py-1.5 text-xs font-medium text-purple hover:bg-purple/20">
            <Sparkle size={13} /> Brain V2
          </Link>
          <button onClick={() => setShowReview(true)} className="relative flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs text-muted hover:text-text">
            <Inbox size={13} /> Review
            {!!(stats && (stats.pending + stats.conflicts)) && <span className="rounded-full bg-warning px-1.5 text-[10px] font-bold text-bg">{stats.pending + stats.conflicts}</span>}
          </button>
          <button onClick={() => setShowDupes(true)} className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs text-muted hover:text-text"><Sparkles size={13} /> Clean</button>
          <button onClick={() => setShowImport(true)} className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs text-muted hover:text-text"><Upload size={13} /> Import</button>
          <button onClick={() => selectMode ? exitSelect() : setSelectMode(true)}
            className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs ${selectMode ? 'border-accent/50 bg-accent/15 text-accent' : 'border-border text-muted hover:text-text'}`}>
            <ListChecks size={13} /> {selectMode ? 'Done' : 'Select'}
          </button>
          <button onClick={() => setModal('new')} className="flex items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-2.5 py-1.5 text-xs font-medium text-accent hover:bg-accent/20"><Plus size={13} /> Add</button>
        </div>
      </div>

      {/* mini stat chips */}
      {stats && (
        <div className="flex flex-wrap gap-2 text-[11px]">
          <Chip label="Total" value={stats.total} />
          <Chip label="Pending" value={stats.pending} tone={stats.pending ? 'warning' : undefined} icon={<Inbox size={11} />} />
          <Chip label="Conflicts" value={stats.conflicts} tone={stats.conflicts ? 'danger' : undefined} icon={<AlertTriangle size={11} />} />
          <Chip label="Stale" value={stats.stale} tone={stats.stale ? 'warning' : undefined} icon={<Clock size={11} />} />
          <button onClick={sweep} disabled={sweeping} className="ml-auto flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-muted hover:text-text disabled:opacity-50">
            <RefreshCw size={11} className={sweeping ? 'animate-spin' : ''} /> {sweeping ? 'Sweeping…' : 'Sweep chat'}
          </button>
        </div>
      )}

      {/* Narrative */}
      <div className="rounded-xl border border-purple/20 bg-purple/5 p-3.5">
        <div className="mb-1.5 flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-xs font-semibold text-purple"><ScrollText size={13} /> TOBI's view of you</span>
          <button onClick={regenNarrative} disabled={narrativeBusy} className="flex items-center gap-1 text-[11px] text-muted hover:text-text">
            <RefreshCw size={11} className={narrativeBusy ? 'animate-spin' : ''} /> {narrative ? 'Regenerate' : 'Generate'}
          </button>
        </div>
        <p className="text-xs leading-relaxed text-text">{narrative || <span className="text-muted">No narrative yet — add a few memories, then generate TOBI's psychological picture of you.</span>}</p>
      </div>

      {/* Search + filters */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex min-w-[220px] flex-1 items-center gap-2 rounded-lg border border-border bg-surface px-3">
          <Search size={15} className="text-muted" />
          <input value={query} onChange={e => setQuery(e.target.value)} placeholder={semantic ? 'Ask your memory…' : 'Search memories…'}
            className="w-full bg-transparent py-2 text-sm text-text outline-none placeholder:text-muted" />
          {query && <button onClick={() => setQuery('')} className="text-muted hover:text-text"><X size={14} /></button>}
        </div>
        <button onClick={() => setSemantic(s => !s)} disabled={!stats?.embeddings}
          title={stats?.embeddings ? 'Semantic search' : 'Install fastembed to enable semantic search'}
          className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-2 text-xs ${semantic ? 'border-accent/50 bg-accent/15 text-accent' : 'border-border text-muted hover:text-text'} disabled:opacity-40`}>
          <Sparkles size={13} /> Semantic
        </button>
        <SortMenu sortBy={sortBy} setSortBy={setSortBy} />
        <button onClick={() => setShowFilters(f => !f)} className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-2 text-xs ${showFilters ? 'border-accent/50 text-accent' : 'border-border text-muted hover:text-text'}`}>
          <Filter size={13} /> Filter
        </button>
      </div>

      {showFilters && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2 text-xs">
          <label className="flex items-center gap-1.5 text-muted">Source
            <select value={source} onChange={e => setSource(e.target.value)} className="rounded border border-border bg-bg px-1.5 py-1 text-text outline-none">
              <option value="all">all</option>
              {sources.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label className="flex cursor-pointer items-center gap-1.5 text-muted">
            <input type="checkbox" checked={staleOnly} onChange={e => setStaleOnly(e.target.checked)} /> stale only
          </label>
        </div>
      )}

      {/* Category tabs */}
      <div className="flex flex-wrap gap-1.5">
        <Tab active={activeCat === 'all'} onClick={() => setActiveCat('all')} color="rgb(var(--muted))" label="All" count={stats?.total} />
        {categories.map(c => (
          <Tab key={c.id} active={activeCat === c.id} onClick={() => setActiveCat(c.id)} color={c.color}
            label={c.label} count={stats?.by_category[c.id]} locked={!!c.is_locked} />
        ))}
      </div>

      {/* Bulk-select action bar */}
      {selectMode && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-accent/40 bg-accent/5 px-3 py-2 text-xs">
          <span className="font-medium text-text">{selected.size} selected</span>
          <button onClick={selectAll} className="text-muted hover:text-text">Select all ({memories.length})</button>
          {selected.size > 0 && <button onClick={() => setSelected(new Set())} className="text-muted hover:text-text">Clear</button>}
          <div className="ml-auto flex items-center gap-2">
            {!confirmDel ? (
              <button onClick={() => setConfirmDel(true)} disabled={selected.size === 0}
                className="flex items-center gap-1.5 rounded-md border border-danger/40 bg-danger/10 px-2.5 py-1.5 font-medium text-danger hover:bg-danger/20 disabled:opacity-40">
                <Trash2 size={13} /> Delete selected
              </button>
            ) : (
              <>
                <span className="text-danger">Delete {selected.size}?</span>
                <button onClick={() => setConfirmDel(false)} className="rounded-md border border-border px-2 py-1.5 text-muted hover:text-text">Cancel</button>
                <button onClick={bulkDelete} disabled={deleting}
                  className="flex items-center gap-1.5 rounded-md border border-danger/50 bg-danger/20 px-2.5 py-1.5 font-medium text-danger hover:bg-danger/30 disabled:opacity-50">
                  {deleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />} Confirm delete
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {/* Memory list */}
      <div className="space-y-1.5">
        {memories.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border py-12 text-center text-sm text-muted">
            No memories here yet. {activeCat === 'all' ? 'Chat with TOBI or import a file to get started.' : 'Add one or pick another category.'}
          </div>
        ) : sorted.map(m => {
          const c = catMap[m.category]
          const color = c?.color ?? '#a78bfa'
          const isSel = selected.has(m.id)
          const onRow = () => selectMode ? toggleSel(m.id) : setModal(m)
          return (
            <motion.button key={m.id} layout onClick={onRow}
              initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
              className={`flex w-full items-center gap-3 overflow-hidden rounded-lg border bg-surface px-3 py-2.5 text-left transition-colors ${isSel ? 'border-accent/60 bg-accent/5' : 'border-border hover:border-overlay/20'}`}>
              {selectMode && (
                <span className={isSel ? 'text-accent' : 'text-muted'}>
                  {isSel ? <CheckSquare size={16} /> : <Square size={16} />}
                </span>
              )}
              <span className="h-8 w-1 shrink-0 rounded-full" style={{ background: color }} />
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm text-text">{m.content}</div>
                <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-muted">
                  <span className="rounded px-1.5 py-0.5 font-medium" style={{ color, background: `${color}1a` }}>{c?.label ?? m.category}</span>
                  <SourceTag source={m.source} />
                  <ConfidenceBar value={m.confidence} />
                  {m.stale && <span className="flex items-center gap-0.5 text-warning"><Clock size={9} /> stale</span>}
                  {typeof m.score === 'number' && <span className="text-accent">· {Math.round(m.score * 100)}% match</span>}
                </div>
              </div>
            </motion.button>
          )
        })}
      </div>

      {modal && <MemoryModal memory={modal} categories={categories} onClose={() => setModal(null)} onSaved={afterChange} />}
      {showImport && <BrainImportModal categories={categories} onClose={() => setShowImport(false)} onDone={(saved, merged) => { setShowImport(false); toast({ kind: 'success', title: 'Imported', detail: `${saved} saved, ${merged} merged` }); afterChange() }} />}
      {showDupes && <CleanDuplicatesModal onClose={() => setShowDupes(false)} onDone={(merged) => { setShowDupes(false); toast({ kind: 'success', title: 'Duplicates cleaned', detail: `${merged} merged` }); afterChange() }} />}
      {showReview && <ReviewInbox onClose={() => setShowReview(false)} onChange={afterChange} />}
    </div>
  )
}

// ── Sort menu ─────────────────────────────────────────────────────────────────
const SORT_OPTIONS = [
  { id: 'default',    label: 'Default',         desc: 'By importance',              Icon: Sparkle },
  { id: 'latest',     label: 'Latest First',    desc: 'Most recent activity',       Icon: CalendarClock },
  { id: 'confidence', label: 'Confidence First', desc: 'High → low confidence',     Icon: TrendingUp },
  { id: 'az',         label: 'A → Z',           desc: 'Alphabetical',               Icon: ArrowDownAZ },
] as const

function SortMenu({ sortBy, setSortBy }: { sortBy: string; setSortBy: (v: string) => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const cur = SORT_OPTIONS.find(o => o.id === sortBy) ?? SORT_OPTIONS[0]
  const CurIcon = cur.Icon

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDoc); document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey) }
  }, [open])

  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen(o => !o)}
        className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-2 text-xs transition-colors ${open ? 'border-accent/50 text-accent' : 'border-border text-muted hover:text-text'}`}>
        <CurIcon size={13} /> {cur.label}
        <ArrowDownUp size={11} className={`opacity-50 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.97 }}
            transition={{ duration: 0.16, ease: 'easeOut' }}
            className="absolute right-0 top-full z-50 mt-1.5 w-56 overflow-hidden rounded-xl border border-border bg-surface/95 p-1 shadow-[0_10px_44px_-10px_rgba(0,0,0,0.55)] ring-1 ring-overlay/[0.04] backdrop-blur-xl">
            {SORT_OPTIONS.map(o => {
              const Icon = o.Icon
              const active = o.id === sortBy
              return (
                <button key={o.id} onClick={() => { setSortBy(o.id); setOpen(false) }}
                  className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors ${active ? 'bg-accent/10 text-accent' : 'text-text hover:bg-bg/60'}`}>
                  <Icon size={14} className={active ? 'text-accent' : 'text-muted'} />
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-medium">{o.label}</div>
                    <div className={`text-[10px] ${active ? 'text-accent/70' : 'text-muted/70'}`}>{o.desc}</div>
                  </div>
                  {active && <Check size={13} className="shrink-0 text-accent" />}
                </button>
              )
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function Tab({ active, onClick, color, label, count, locked }: { active: boolean; onClick: () => void; color: string; label: string; count?: number; locked?: boolean }) {
  return (
    <button onClick={onClick}
      className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors ${active ? 'text-text' : 'text-muted hover:text-text'}`}
      style={active ? { borderColor: color, background: `${color}1a` } : { borderColor: 'rgb(var(--border))' }}>
      <span className="h-2 w-2 rounded-full" style={{ background: color }} />
      {label}{locked ? ' 🔒' : ''}
      {typeof count === 'number' && <span className="text-[10px] text-muted">{count}</span>}
    </button>
  )
}

const SOURCE_META: Record<string, { icon: React.ReactNode; label: string }> = {
  import: { icon: <FileText size={10} />, label: 'imported' },
  chat: { icon: <MessagesSquare size={10} />, label: 'chat' },
  auto: { icon: <Wand2 size={10} />, label: 'auto-learned' },
  manual: { icon: <Pencil size={10} />, label: 'manual' },
  owner: { icon: <Pencil size={10} />, label: 'manual' },
}
function SourceTag({ source }: { source: string }) {
  const meta = SOURCE_META[source] ?? { icon: <CircleDot size={10} />, label: source }
  return <span className="flex items-center gap-1" title={`Source: ${meta.label}`}>{meta.icon}{meta.label}</span>
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round((value ?? 0) * 100)
  const color = value >= 0.8 ? '#3fb950' : value >= 0.6 ? '#d29922' : '#f85149'
  return (
    <span className="flex items-center gap-1" title={`Confidence ${pct}%`}>
      <span className="h-1.5 w-10 overflow-hidden rounded-full bg-border">
        <span className="block h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
      </span>
      <span className="font-mono">{pct}%</span>
    </span>
  )
}

function Chip({ label, value, tone, icon }: { label: string; value: number; tone?: 'warning' | 'danger'; icon?: React.ReactNode }) {
  const cls = tone === 'danger' ? 'border-danger/40 text-danger' : tone === 'warning' ? 'border-warning/40 text-warning' : 'border-border text-muted'
  return <span className={`flex items-center gap-1 rounded-full border px-2 py-0.5 ${cls}`}>{icon}{label} <span className="font-semibold text-text">{value}</span></span>
}

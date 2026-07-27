import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Brain as BrainIcon, Lock, Unlock, RefreshCw, Upload, Sparkles, ArrowLeft,
  ThumbsUp, ThumbsDown, XCircle, Trash2, Archive, CheckCircle2, ChevronDown,
  ChevronRight, Loader2, ShieldAlert, Search, Database, GitMerge, Eye, Play,
  X, Filter, CheckSquare, Square, Plus, CalendarClock, TrendingUp, ArrowDownAZ, Eraser, Pencil,
} from 'lucide-react'
import { ActionButton } from '../components/async-ui'
import {
  type V2Memory, type V2Stats, type V2JobStatus, type V2Candidate,
  type V2MigrationStatus, type V2MigrationItem, type V2RecallItem,
  type V2Influence, type V2CleanupProposal,
  v2Stats, v2Profile, v2Memories, v2SetStatus, v2EditMemory, v2Feedback, v2Influence,
  v2Purge, v2Recall, v2Remember, v2ImportCreate, v2ImportCandidates, v2ImportCommand, v2ImportStatus,
  v2ImportDecide, v2MigrationCreate, v2MigrationItems, v2MigrationCommand,
  v2MigrationDecide, v2CleanupPreview, v2CleanupApply,
} from '../api.brainV2'
import { useToast } from '../context/ToastProvider'
import { ImportTab } from './brainv2/ImportTab'
import { MigrationTab, TellTab } from './brainv2/MigrationTab'
import { Badge, MemoryRow, STATUSES, SortMenu, StatTile, TYPES, Tab, errMsg, typeMeta } from './brainv2/parts'

// ── page ──────────────────────────────────────────────────────────────────────
export default function BrainV2() {
  const { toast } = useToast()
  const [tab, setTab] = useState<Tab>('overview')
  const [stats, setStats] = useState<V2Stats | null>(null)
  const [profile, setProfile] = useState<{ profile: string; version: string } | null>(null)
  const [memories, setMemories] = useState<V2Memory[]>([])
  const [status, setStatus] = useState('all')
  const [mtype, setMtype] = useState('all')
  const [cleanup, setCleanup] = useState<V2CleanupProposal[] | null>(null)
  const [busy, setBusy] = useState(false)

  // library controls (V1-parity UX)
  const [query, setQuery] = useState('')
  const [semantic, setSemantic] = useState(false)
  const [recallHits, setRecallHits] = useState<V2RecallItem[] | null>(null)
  const [recallBusy, setRecallBusy] = useState(false)
  const [sortBy, setSortBy] = useState('default')
  const [showFilters, setShowFilters] = useState(false)
  const [fAuthority, setFAuthority] = useState('all')
  const [fExplicit, setFExplicit] = useState('all')
  const [fTrust, setFTrust] = useState('all')
  const [fSensitive, setFSensitive] = useState(false)
  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [confirmDel, setConfirmDel] = useState(false)
  const [bulkBusy, setBulkBusy] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [addText, setAddText] = useState('')
  const [addBusy, setAddBusy] = useState(false)

  const reload = useCallback(async () => {
    try {
      const [s, p, m] = await Promise.all([v2Stats(), v2Profile(), v2Memories({ limit: 500 })])
      setStats(s); setProfile(p); setMemories(m)
    } catch (e) { toast({ kind: 'error', title: errMsg(e) }) }
  }, [toast])

  useEffect(() => { void reload() }, [reload])

  // semantic search = live recall preview (what TOBI would actually retrieve)
  useEffect(() => {
    if (!semantic || !query.trim()) { setRecallHits(null); return }
    const t = setTimeout(async () => {
      setRecallBusy(true)
      try { setRecallHits(await v2Recall(query.trim(), 'agent')) } catch { setRecallHits([]) }
      finally { setRecallBusy(false) }
    }, 400)
    return () => clearTimeout(t)
  }, [semantic, query])

  const runCleanup = useCallback(async () => {
    setBusy(true)
    try { setCleanup((await v2CleanupPreview()).proposals) }
    catch (e) { toast({ kind: 'error', title: errMsg(e) }) }
    finally { setBusy(false) }
  }, [toast])

  const applyCleanup = useCallback(async (p: V2CleanupProposal) => {
    try {
      await v2CleanupApply([p])
      toast({ kind: 'success', title: 'Applied' })
      setCleanup(c => (c || []).filter(x => x !== p))
      void reload()
    } catch (e) { toast({ kind: 'error', title: errMsg(e) }) }
  }, [toast, reload])

  const total = memories.length
  const statusCounts = useMemo(() => {
    const c: Record<string, number> = {}
    for (const m of memories) c[m.status] = (c[m.status] ?? 0) + 1
    return c
  }, [memories])
  const typeCounts = useMemo(() => {
    const c: Record<string, number> = {}
    for (const m of memories) c[m.memory_type] = (c[m.memory_type] ?? 0) + 1
    return c
  }, [memories])

  const filtered = useMemo(() => {
    let list = memories
    if (status !== 'all') list = list.filter(m => m.status === status)
    if (mtype !== 'all') list = list.filter(m => m.memory_type === mtype)
    if (fAuthority !== 'all') list = list.filter(m => m.authority === fAuthority)
    if (fExplicit !== 'all') list = list.filter(m => m.explicitness === fExplicit)
    if (fTrust !== 'all') list = list.filter(m => m.trust === fTrust)
    if (fSensitive) list = list.filter(m => m.sensitive)
    const q = query.trim().toLowerCase()
    if (q && !semantic) {
      list = list.filter(m => m.distilled_text.toLowerCase().includes(q)
        || m.behavior_implication.toLowerCase().includes(q)
        || m.tags.some(t => t.toLowerCase().includes(q)))
    }
    return list
  }, [memories, status, mtype, fAuthority, fExplicit, fTrust, fSensitive, query, semantic])

  const sorted = useMemo(() => {
    const list = [...filtered]
    switch (sortBy) {
      case 'latest': list.sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || '')); break
      case 'confidence': list.sort((a, b) => b.confidence - a.confidence); break
      case 'az': list.sort((a, b) => a.distilled_text.localeCompare(b.distilled_text)); break
      default: list.sort((a, b) => (b.quality_score - a.quality_score) || (b.confidence - a.confidence))
    }
    return list
  }, [filtered, sortBy])

  // what the list actually shows: semantic recall order, or the filtered+sorted set
  const display = useMemo((): { m: V2Memory; matchPct?: number }[] => {
    if (semantic && query.trim() && recallHits) {
      const byId = new Map(memories.map(m => [m.id, m]))
      return recallHits.filter(r => byId.has(r.memory_id))
        .map(r => ({ m: byId.get(r.memory_id)!, matchPct: Math.round((r.signals.semantic ?? 0) * 100) }))
    }
    return sorted.map(m => ({ m }))
  }, [semantic, query, recallHits, memories, sorted])

  const toggleSel = useCallback((id: number) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }, [])

  const bulk = useCallback(async (label: string, ids: number[], fn: (id: number) => Promise<unknown>) => {
    if (ids.length === 0) { toast({ kind: 'error', title: `Nothing selected is eligible to ${label.toLowerCase()}` }); return }
    setBulkBusy(true)
    let done = 0, failed = 0
    for (const id of ids) { try { await fn(id); done++ } catch { failed++ } }
    toast({ kind: failed ? 'error' : 'success', title: `${label} ${done}${failed ? ` · ${failed} failed` : ''}` })
    setSelected(new Set()); setConfirmDel(false); setBulkBusy(false)
    void reload()
  }, [toast, reload])

  const selIds = useCallback((pred: (m: V2Memory) => boolean) =>
    memories.filter(m => selected.has(m.id) && pred(m)).map(m => m.id), [memories, selected])

  const addSubmit = useCallback(async () => {
    if (!addText.trim()) return
    setAddBusy(true)
    try {
      const res = await v2Remember(addText.trim())
      const v2 = res.v2
      toast({
        kind: 'success', title: 'Remembered',
        detail: v2?.outcome ? `Quality gate: ${v2.outcome}${v2.status ? ` → ${v2.status}` : ''}` : res.action,
      })
      setAddText(''); setShowAdd(false)
      void reload()
    } catch (e) { toast({ kind: 'error', title: errMsg(e) }) }
    finally { setAddBusy(false) }
  }, [addText, toast, reload])

  return (
    <div className="space-y-4 p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-purple/30 bg-purple/10 text-purple"><BrainIcon size={18} /></div>
          <div>
            <h1 className="flex items-center gap-2 text-lg font-bold text-heading">Brain V2 <Badge tone="purple">typed memory</Badge></h1>
            <p className="text-[11px] text-muted">Quality-gated owner memory · {total} memories
              {stats && (stats.vault_unlocked
                ? <span className="ml-1 inline-flex items-center gap-0.5 text-success"><Unlock size={10} /> vault unlocked</span>
                : <span className="ml-1 inline-flex items-center gap-0.5 text-warning"><Lock size={10} /> vault locked — sensitive memory redacted</span>)}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link to="/brain/legacy" className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs text-muted hover:text-text"><ArrowLeft size={13} /> Legacy Brain</Link>
          <button onClick={() => { setTab('overview'); void runCleanup() }}
            className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs text-muted hover:text-text"><Eraser size={13} /> Clean</button>
          <button onClick={() => { setTab('library'); setShowAdd(true) }}
            className="flex items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-2.5 py-1.5 text-xs font-medium text-accent hover:bg-accent/20"><Plus size={13} /> Add</button>
          <ActionButton onAction={() => reload()} icon={<RefreshCw size={13} />} className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs text-muted hover:text-text"> Refresh</ActionButton>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {([['overview', 'Overview', Database], ['library', 'Library', BrainIcon], ['import', 'Import', Upload],
        ['migration', 'Migration', GitMerge], ['ask', 'Tell TOBI', Sparkles]] as [Tab, string, typeof Database][]).map(([id, label, Icon]) => (
          <button key={id} onClick={() => setTab(id)}
            className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs ${tab === id ? 'border-accent/50 bg-accent/15 text-accent' : 'border-border text-muted hover:text-text'}`}>
            <Icon size={13} /> {label}
            {id === 'ask' && <span className="rounded-full bg-warning/15 px-1.5 text-[9px] font-medium text-warning">soon</span>}
          </button>
        ))}
      </div>

      {tab === 'overview' && stats && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            <StatTile label="Active" value={stats.by_status.active ?? 0} tone="text-success" />
            <StatTile label="Pending review" value={stats.by_status.pending ?? 0} tone={stats.by_status.pending ? 'text-warning' : undefined} />
            <StatTile label="Conflicted" value={stats.conflicted} tone={stats.conflicted ? 'text-danger' : undefined} />
            <StatTile label="Sensitive" value={stats.sensitive} />
            <StatTile label="Aging (14d+)" value={stats.aging_pending} tone={stats.aging_pending ? 'text-warning' : undefined} />
            <StatTile label="Rejected" value={stats.by_status.rejected ?? 0} />
          </div>
          <div className="rounded-xl border border-purple/20 bg-purple/5 p-3.5">
            <p className="mb-1.5 text-xs font-semibold text-purple">Stable behavior profile <span className="font-normal text-muted">· v{profile?.version} · always in context (≤800 tokens)</span></p>
            <pre className="whitespace-pre-wrap font-sans text-xs leading-relaxed text-text">{profile?.profile || <span className="text-muted">Empty — activate memories to build the profile.</span>}</pre>
          </div>
          <div className="rounded-xl border border-border bg-surface/40 p-3.5">
            <div className="mb-1.5 flex items-center justify-between">
              <p className="text-xs font-semibold text-text">Cleanup center</p>
              <button disabled={busy} onClick={runCleanup} className="flex items-center gap-1 text-[11px] text-muted hover:text-text">
                {busy ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />} Scan for recommendations
              </button>
            </div>
            {cleanup === null ? <p className="text-xs text-muted">Recommends merges, archives, and revalidation. Nothing applies without your confirmation.</p>
              : cleanup.length === 0 ? <p className="text-xs text-success">Nothing to clean up.</p>
                : cleanup.map((p, i) => (
                  <div key={i} className="flex items-center gap-2 border-t border-border py-1.5 first:border-0">
                    <Badge tone={p.action === 'merge' ? 'accent' : p.action === 'archive' ? 'warning' : 'purple'}>{p.action}</Badge>
                    <span className="flex-1 text-xs text-muted">{p.reason} (#{p.memory_id ?? `${p.keep_id}←${p.merge_id}`})</span>
                    <button onClick={() => applyCleanup(p)} className="rounded-lg border border-border px-2 py-0.5 text-[11px] text-muted hover:text-text">Apply</button>
                  </div>
                ))}
          </div>
        </div>
      )}

      {tab === 'library' && (
        <div className="space-y-2.5">
          {/* search + controls */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex min-w-[220px] flex-1 items-center gap-2 rounded-lg border border-border bg-surface px-3">
              <Search size={15} className="text-muted" />
              <input value={query} onChange={e => setQuery(e.target.value)}
                placeholder={semantic ? 'Ask your memory…' : 'Search memories…'}
                className="w-full bg-transparent py-2 text-sm text-text outline-none placeholder:text-muted" />
              {recallBusy && <Loader2 size={14} className="animate-spin text-muted" />}
              {query && <button onClick={() => setQuery('')} className="text-muted hover:text-text"><X size={14} /></button>}
            </div>
            <button onClick={() => setSemantic(s => !s)} title="Rank by meaning using TOBI's live recall pipeline"
              className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-2 text-xs transition-colors ${semantic ? 'border-accent/50 bg-accent/15 text-accent' : 'border-border text-muted hover:text-text'}`}>
              <Sparkles size={13} /> Semantic
            </button>
            <SortMenu sortBy={sortBy} setSortBy={setSortBy} />
            <button onClick={() => setShowFilters(f => !f)}
              className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-2 text-xs transition-colors ${showFilters ? 'border-accent/50 text-accent' : 'border-border text-muted hover:text-text'}`}>
              <Filter size={13} /> Filter
            </button>
            <button onClick={() => setSelectMode(s => { if (s) { setSelected(new Set()); setConfirmDel(false) } return !s })}
              className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-2 text-xs transition-colors ${selectMode ? 'border-accent/50 bg-accent/15 text-accent' : 'border-border text-muted hover:text-text'}`}>
              <CheckSquare size={13} /> Select
            </button>
          </div>

          {showAdd && (
            <div className="space-y-2 rounded-xl border border-accent/30 bg-accent/5 p-3">
              <p className="text-xs text-muted">Tell TOBI something to remember. It runs through the V2 quality gate — strong, explicit, conflict-free facts activate immediately; everything else lands in pending for your review.</p>
              <textarea value={addText} onChange={e => setAddText(e.target.value)} rows={2} autoFocus
                onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) void addSubmit() }}
                className="w-full rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs text-text"
                placeholder="e.g. Weekly reports must always be in Vietnamese, delivered before Friday noon." />
              <div className="flex items-center gap-2">
                <button disabled={addBusy || !addText.trim()} onClick={() => void addSubmit()}
                  className="flex items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/20 disabled:opacity-50">
                  {addBusy ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />} Remember
                </button>
                <button onClick={() => { setShowAdd(false); setAddText('') }}
                  className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted hover:text-text">Cancel</button>
              </div>
            </div>
          )}

          {showFilters && (
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2 text-xs">
              <label className="flex items-center gap-1.5 text-muted">Authority
                <select value={fAuthority} onChange={e => setFAuthority(e.target.value)} className="rounded border border-border bg-bg px-1.5 py-1 text-text outline-none">
                  <option value="all">all</option><option value="hard">hard rules</option><option value="soft">soft</option>
                </select>
              </label>
              <label className="flex items-center gap-1.5 text-muted">Origin
                <select value={fExplicit} onChange={e => setFExplicit(e.target.value)} className="rounded border border-border bg-bg px-1.5 py-1 text-text outline-none">
                  <option value="all">all</option><option value="explicit">explicit</option><option value="inferred">inferred</option>
                </select>
              </label>
              <label className="flex items-center gap-1.5 text-muted">Trust
                <select value={fTrust} onChange={e => setFTrust(e.target.value)} className="rounded border border-border bg-bg px-1.5 py-1 text-text outline-none">
                  <option value="all">all</option><option value="trusted">trusted</option><option value="untrusted">imported</option>
                </select>
              </label>
              <label className="flex cursor-pointer items-center gap-1.5 text-muted">
                <input type="checkbox" checked={fSensitive} onChange={e => setFSensitive(e.target.checked)} /> sensitive only
              </label>
            </div>
          )}

          {/* status chips */}
          <div className="flex flex-wrap gap-1.5">
            {['all', ...STATUSES].map(s => (
              <button key={s} onClick={() => setStatus(s)}
                className={`rounded-full border px-2.5 py-1 text-[11px] ${status === s ? 'border-accent/50 bg-accent/15 text-accent' : 'border-border text-muted hover:text-text'}`}>
                {s} <span className="opacity-70">{s === 'all' ? total : statusCounts[s] ?? 0}</span>
              </button>
            ))}
          </div>

          {/* type chips (colored, with counts) */}
          <div className="flex flex-wrap gap-1.5">
            <button onClick={() => setMtype('all')}
              className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] transition-colors ${mtype === 'all' ? 'text-text' : 'text-muted hover:text-text'}`}
              style={mtype === 'all' ? { borderColor: 'rgb(var(--muted))', background: 'rgb(var(--muted) / 0.1)' } : { borderColor: 'rgb(var(--border))' }}>
              <span className="h-2 w-2 rounded-full bg-muted" /> All types
            </button>
            {TYPES.map(t => {
              const meta = typeMeta(t)
              const active = mtype === t
              return (
                <button key={t} onClick={() => setMtype(active ? 'all' : t)}
                  className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] transition-colors ${active ? 'text-text' : 'text-muted hover:text-text'}`}
                  style={active ? { borderColor: meta.color, background: `${meta.color}1a` } : { borderColor: 'rgb(var(--border))' }}>
                  <span className="h-2 w-2 rounded-full" style={{ background: meta.color }} />
                  {meta.label} <span className="opacity-70">{typeCounts[t] ?? 0}</span>
                </button>
              )
            })}
          </div>

          {/* bulk-select action bar */}
          {selectMode && (
            <div className="flex flex-wrap items-center gap-2 rounded-lg border border-accent/40 bg-accent/5 px-3 py-2 text-xs">
              <span className="font-medium text-text">{selected.size} selected</span>
              <button onClick={() => setSelected(new Set(display.map(d => d.m.id)))} className="text-muted hover:text-text">Select all ({display.length})</button>
              {selected.size > 0 && <button onClick={() => setSelected(new Set())} className="text-muted hover:text-text">Clear</button>}
              <div className="ml-auto flex flex-wrap items-center gap-1.5">
                <button disabled={bulkBusy || selected.size === 0}
                  onClick={() => bulk('Approved', selIds(m => m.status === 'pending'), id => v2SetStatus(id, 'active'))}
                  className="flex items-center gap-1 rounded-md border border-success/40 bg-success/10 px-2.5 py-1.5 text-success hover:bg-success/20 disabled:opacity-40">
                  <CheckCircle2 size={13} /> Approve
                </button>
                <button disabled={bulkBusy || selected.size === 0}
                  onClick={() => bulk('Rejected', selIds(m => m.status !== 'rejected'), id => v2SetStatus(id, 'rejected'))}
                  className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1.5 text-muted hover:text-warning disabled:opacity-40">
                  <XCircle size={13} /> Reject
                </button>
                <button disabled={bulkBusy || selected.size === 0}
                  onClick={() => bulk('Archived', selIds(m => m.status !== 'archived'), id => v2SetStatus(id, 'archived'))}
                  className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1.5 text-muted hover:text-text disabled:opacity-40">
                  <Archive size={13} /> Archive
                </button>
                {!confirmDel ? (
                  <button disabled={bulkBusy || selected.size === 0} onClick={() => setConfirmDel(true)}
                    className="flex items-center gap-1 rounded-md border border-danger/40 bg-danger/10 px-2.5 py-1.5 font-medium text-danger hover:bg-danger/20 disabled:opacity-40">
                    <Trash2 size={13} /> Delete
                  </button>
                ) : (
                  <>
                    <span className="text-danger">Purge {selected.size} permanently?</span>
                    <button onClick={() => setConfirmDel(false)} className="rounded-md border border-border px-2 py-1.5 text-muted hover:text-text">Cancel</button>
                    <button disabled={bulkBusy}
                      onClick={() => bulk('Purged', [...selected], id => v2Purge(id))}
                      className="flex items-center gap-1 rounded-md border border-danger/50 bg-danger/20 px-2.5 py-1.5 font-medium text-danger hover:bg-danger/30 disabled:opacity-50">
                      {bulkBusy ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />} Confirm
                    </button>
                  </>
                )}
              </div>
            </div>
          )}

          {semantic && query.trim() && (
            <p className="text-[11px] text-muted">
              Semantic mode shows what TOBI would <span className="text-text">actually recall</span> for this query — ranked and budgeted, active memories only.
            </p>
          )}

          {display.length === 0
            ? <div className="rounded-xl border border-dashed border-border py-10 text-center text-xs text-muted">
              {semantic && query.trim()
                ? 'Nothing recalled for this query — irrelevant memory stays out by design.'
                : query.trim() || status !== 'all' || mtype !== 'all'
                  ? 'No memories match these filters.'
                  : 'No V2 memories yet — remember something, import, or run the migration.'}
            </div>
            : <div className="space-y-1.5">{display.map(({ m, matchPct }) => (
              <MemoryRow key={m.id} m={m} onChanged={() => void reload()} matchPct={matchPct}
                selectMode={selectMode} selected={selected.has(m.id)} onToggleSel={() => toggleSel(m.id)} />
            ))}</div>}
        </div>
      )}

      {tab === 'import' && <ImportTab />}
      {tab === 'migration' && <MigrationTab />}
      {tab === 'ask' && <TellTab />}
    </div>
  )
}

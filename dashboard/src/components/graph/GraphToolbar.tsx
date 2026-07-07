import { useState } from 'react'
import {
  Search, RefreshCw, Sparkles, Link2, Zap, ZapOff, Plus, X, SlidersHorizontal,
} from 'lucide-react'
import { searchGraph, type GraphSource, type GraphSearchResult } from '../../api'

type Props = {
  sources: GraphSource[]
  domain: string
  onDomain: (d: string) => void
  performance: boolean
  onTogglePerformance: () => void
  connectMode: boolean
  onToggleConnect: () => void
  onAddNode: () => void
  onRefresh: () => void
  syncing: boolean
  minWeight: number
  onMinWeight: (v: number) => void
  category: string
  onCategory: (v: string) => void
  onFocusResult: (id: number) => void
}

const DOMAIN_ORDER = ['all', 'memory', 'task', 'project', 'notion', 'github', 'gdrive', 'local', 'manual']
const DOMAIN_LABEL: Record<string, string> = {
  all: 'All', memory: 'Memory', task: 'Tasks', project: 'Projects', notion: 'Notion',
  github: 'GitHub', gdrive: 'Drive', local: 'Local', manual: 'Notes',
}

export default function GraphToolbar(p: Props) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<GraphSearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [showFilters, setShowFilters] = useState(false)

  const countFor = (d: string) => {
    if (d === 'all') return p.sources.reduce((a, s) => a + (s.nodes || 0), 0)
    const map: Record<string, string> = { gdrive: 'gdrive' }
    const src = p.sources.find(s => s.domain === (map[d] || d))
    return src?.nodes ?? undefined
  }

  const runSearch = async (text: string) => {
    setQ(text)
    if (text.trim().length < 2) { setResults([]); return }
    setSearching(true)
    try { setResults((await searchGraph(text)).results) } catch { setResults([]) } finally { setSearching(false) }
  }

  return (
    <div className="absolute left-3 right-3 top-3 z-10 flex flex-col gap-2 rounded-2xl border border-accent/15 bg-[#07101d]/82 px-3 py-2 shadow-[0_18px_70px_rgb(0_0_0/0.28),0_0_36px_rgb(var(--accent)/0.08)] backdrop-blur-xl">
      <div className="flex flex-wrap items-center gap-2">
        {/* domain switcher */}
        <div className="flex flex-wrap items-center gap-1">
          {DOMAIN_ORDER.map(d => {
            const c = countFor(d)
            const active = p.domain === d
            return (
              <button key={d} onClick={() => p.onDomain(d)}
                className={`rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors ${active ? 'border-accent/50 bg-accent/15 text-accent shadow-[0_0_18px_rgb(var(--accent)/0.12)]' : 'border-transparent text-muted hover:border-border hover:bg-bg/45 hover:text-text'}`}>
                {DOMAIN_LABEL[d]}{c != null && c > 0 ? <span className="ml-1 opacity-60">{c}</span> : null}
              </button>
            )
          })}
        </div>

        <div className="ml-auto flex items-center gap-1.5">
          {/* search */}
          <div className="relative">
            <Search size={13} className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-muted" />
            <input value={q} onChange={e => runSearch(e.target.value)} placeholder="Search · fly-to"
              className="w-52 rounded-lg border border-border/80 bg-bg/70 py-1.5 pl-7 pr-6 text-xs text-text outline-none shadow-inner focus:border-accent/50" />
            {q && <button onClick={() => { setQ(''); setResults([]) }} className="absolute right-2 top-1/2 -translate-y-1/2 text-muted hover:text-text"><X size={12} /></button>}
            {results.length > 0 && (
              <div className="absolute right-0 top-full z-20 mt-1 max-h-64 w-72 overflow-y-auto rounded-xl border border-accent/20 bg-[#07101d]/95 shadow-2xl backdrop-blur-xl">
                {results.map(r => (
                  <button key={r.id} onClick={() => { p.onFocusResult(r.id); setResults([]); setQ('') }}
                    className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs text-text hover:bg-accent/10">
                    <span className="truncate">{r.title}</span>
                    <span className="shrink-0 text-[9px] uppercase text-muted">{r.domain}</span>
                  </button>
                ))}
              </div>
            )}
            {searching && <span className="absolute -bottom-4 left-1 text-[9px] text-muted">searching…</span>}
          </div>

          <button onClick={() => setShowFilters(s => !s)} title="Filters"
            className={`rounded-lg border p-1.5 ${showFilters ? 'border-accent/50 bg-accent/10 text-accent' : 'border-border text-muted hover:bg-bg/45 hover:text-text'}`}>
            <SlidersHorizontal size={14} />
          </button>
          <button onClick={p.onToggleConnect} title="Connect two nodes"
            className={`rounded-lg border p-1.5 ${p.connectMode ? 'border-purple/60 bg-purple/15 text-purple shadow-[0_0_18px_rgb(var(--purple)/0.16)]' : 'border-border text-muted hover:bg-bg/45 hover:text-text'}`}>
            <Link2 size={14} />
          </button>
          <button onClick={p.onAddNode} title="Add node"
            className="rounded-lg border border-border p-1.5 text-muted hover:bg-bg/45 hover:text-text"><Plus size={14} /></button>
          <button onClick={p.onTogglePerformance} title={p.performance ? 'Performance mode ON' : 'Full neuron FX'}
            className={`rounded-lg border p-1.5 ${p.performance ? 'border-warning/50 bg-warning/10 text-warning' : 'border-border text-muted hover:bg-bg/45 hover:text-text'}`}>
            {p.performance ? <ZapOff size={14} /> : <Zap size={14} />}
          </button>
          <button onClick={p.onRefresh} disabled={p.syncing} title="Sync + refresh"
            className="flex items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-2.5 py-1.5 text-xs font-semibold text-accent shadow-[0_0_18px_rgb(var(--accent)/0.10)] hover:bg-accent/20 disabled:opacity-50">
            <RefreshCw size={13} className={p.syncing ? 'animate-spin' : ''} /> Sync
          </button>
        </div>
      </div>

      {showFilters && (
        <div className="flex flex-wrap items-center gap-3 border-t border-accent/15 pt-2 text-xs text-muted">
          <Sparkles size={12} className="text-purple" />
          <label className="flex items-center gap-1.5">
            Category
            <input value={p.category} onChange={e => p.onCategory(e.target.value)} placeholder="any"
              className="w-28 rounded border border-border/80 bg-bg/70 px-2 py-1 text-text outline-none focus:border-accent/50" />
          </label>
          <label className="flex items-center gap-1.5">
            Min link strength · <span className="tabular-nums text-text">{p.minWeight.toFixed(2)}</span>
            <input type="range" min={0} max={1} step={0.05} value={p.minWeight}
              onChange={e => p.onMinWeight(Number(e.target.value))}
              className="h-1 w-32 cursor-pointer appearance-none rounded-full bg-border accent-accent" />
          </label>
        </div>
      )}
    </div>
  )
}

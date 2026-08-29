import { useEffect, useRef, useState, useCallback } from 'react'
import { softFail } from '../lib/report'
import { BrainCircuit, RefreshCw, Activity, Cpu, Orbit, RadioTower, Share2 } from 'lucide-react'
import { getGraph, getGraphSources, getGraphTimeline, getGraphCommunities, syncGraph, createGraphNode, createGraphEdge, saveGraphLayout, type GraphData, type GraphNode, type GraphSource, type TimelineEvent, type GraphCommunity } from '../api.graph'
import { useToast } from '../context/ToastProvider'
import ForceGraphCanvas, { type CanvasHandle } from '../components/graph/ForceGraphCanvas'
import NodeDetailPanel from '../components/graph/NodeDetailPanel'
import GraphToolbar from '../components/graph/GraphToolbar'
import GraphLegend from '../components/graph/GraphLegend'
import TimelineScrubber from '../components/graph/TimelineScrubber'
import { DEFAULT_LAYOUT, LAYOUTS, type LayoutMode } from '../components/graph/layouts'
import { publishGraphSnapshot, refreshGraphSnapshot } from '../components/graph/graphSnapshot'

const EMPTY: GraphData = { nodes: [], edges: [] }
const LAYOUT_KEY = 'tobi.graph.layout.v2'
/** The first release used ids that did not match their labels; `orbit` then meant Clusters.
 *  A separate key means the migration is unambiguous instead of guessing at a shared name. */
const LEGACY_KEY = 'tobi.graph.layout'
const LEGACY_IDS: Record<string, LayoutMode> = {
  orbit: 'clusters', radial: 'orbit', lanes: 'columns', force: 'free',
}

/** Remember how the owner likes to see the map, so the page opens the way he left it. */
function storedLayout(): LayoutMode {
  try {
    const saved = localStorage.getItem(LAYOUT_KEY)
    if (saved && LAYOUTS.some(l => l.id === saved)) return saved as LayoutMode
    const legacy = localStorage.getItem(LEGACY_KEY)
    if (legacy && LEGACY_IDS[legacy]) return LEGACY_IDS[legacy]
  } catch { /* private mode / storage disabled — the default is fine */ }
  return DEFAULT_LAYOUT
}

export default function Graph() {
  const { toast } = useToast()
  const [data, setData] = useState<GraphData>(EMPTY)
  const [sources, setSources] = useState<GraphSource[]>([])
  const [communities, setCommunities] = useState<GraphCommunity[]>([])
  const [events, setEvents] = useState<TimelineEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)

  // filters
  const [domain, setDomain] = useState('all')
  const [category, setCategory] = useState('')
  const [minWeight, setMinWeight] = useState(0)
  const [dateTo, setDateTo] = useState<string | undefined>(undefined)
  // counted from the unfiltered graph, so the chips stay right while a filter is applied
  const [domainCounts, setDomainCounts] = useState<Record<string, number>>({})

  // ui state
  const [layout, setLayout] = useState<LayoutMode>(storedLayout)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [performance, setPerformance] = useState(false)
  const [connectMode, setConnectMode] = useState(false)
  const [connectFirst, setConnectFirst] = useState<GraphNode | null>(null)
  const [highlightIds, setHighlightIds] = useState<Set<number>>(new Set())

  const canvasRef = useRef<CanvasHandle>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const [dims, setDims] = useState({ w: 800, h: 600 })

  // size the canvas to its container
  useEffect(() => {
    if (!wrapRef.current) return
    const el = wrapRef.current
    const ro = new ResizeObserver(() => setDims({ w: el.clientWidth, h: el.clientHeight }))
    ro.observe(el)
    setDims({ w: el.clientWidth, h: el.clientHeight })
    return () => ro.disconnect()
  }, [])

  const pickLayout = useCallback((mode: LayoutMode) => {
    setLayout(mode)
    try { localStorage.setItem(LAYOUT_KEY, mode) } catch { /* not worth surfacing */ }
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [g, s, t, c] = await Promise.all([
        getGraph({ domain, category: category || undefined, min_weight: minWeight, date_to: dateTo }),
        getGraphSources(),
        getGraphTimeline(),
        getGraphCommunities(),
      ])
      setData(g); setSources(s.sources); setEvents(t.events); setCommunities(c.communities)
      if (domain === 'all' && !category) {
        const counts: Record<string, number> = {}
        for (const node of g.nodes) counts[node.domain] = (counts[node.domain] || 0) + 1
        setDomainCounts(counts)
        // hand the full graph to the shared store, so every embedded sigil elsewhere in the
        // app is already current the moment the owner navigates away from this page
        publishGraphSnapshot(g)
      }
    } catch (e) {
      toast({ kind: 'error', title: 'Could not load graph', detail: (e as Error).message })
    } finally { setLoading(false) }
  }, [domain, category, minWeight, dateTo, toast])

  useEffect(() => { load() }, [load])

  const refresh = async () => {
    setSyncing(true)
    try {
      const res = await syncGraph('all') as Record<string, unknown>
      await load()
      // a sync can add nodes the current filter hides, so make the shared copy re-read too
      void refreshGraphSnapshot(true)
      toast({ kind: 'success', title: 'Graph synced', detail: summarize(res) })
    } catch (e) {
      toast({ kind: 'error', title: 'Sync failed', detail: (e as Error).message })
    } finally { setSyncing(false) }
  }

  const focusNode = useCallback((id: number) => {
    setSelectedId(id)
    setHighlightIds(new Set([id]))
    canvasRef.current?.focusNode(id)
  }, [])

  const onConnectPick = useCallback(async (n: GraphNode) => {
    if (!connectFirst) {
      setConnectFirst(n); setHighlightIds(new Set([n.id]))
      toast({ kind: 'info', title: 'Pick a second node', detail: `Linking from “${n.title.slice(0, 30)}”` })
      return
    }
    if (n.id === connectFirst.id) { setConnectFirst(null); setHighlightIds(new Set()); return }
    try {
      await createGraphEdge(connectFirst.id, n.id, 'manual')
      toast({ kind: 'success', title: 'Linked' })
      setConnectFirst(null); setConnectMode(false); setHighlightIds(new Set())
      await load()
    } catch (e) { toast({ kind: 'error', title: 'Link failed', detail: (e as Error).message }) }
  }, [connectFirst, toast, load])

  const addNode = async () => {
    const title = window.prompt('New node title')
    if (!title || !title.trim()) return
    try {
      const n = await createGraphNode({ title: title.trim() })
      await load()
      toast({ kind: 'success', title: 'Node created' })
      setTimeout(() => focusNode(n.id), 300)
    } catch (e) { toast({ kind: 'error', title: 'Create failed', detail: (e as Error).message }) }
  }

  // Only reachable in Free mode, where dragging is what pins a node.
  const pin = useCallback((n: any) => {
    saveGraphLayout([{ id: n.id, x: n.x, y: n.y, pinned: true }]).catch(softFail('the graph'))
  }, [])

  const empty = !loading && data.nodes.length === 0
  const activeSources = sources.filter(s => s.available).length
  const density = data.nodes.length ? Math.round((data.edges.length / data.nodes.length) * 10) / 10 : 0

  return (
    <div className="relative flex h-full flex-col overflow-hidden bg-bg">
      <div className="pointer-events-none absolute inset-0 opacity-80">
        <div className="absolute -left-32 top-10 h-80 w-80 rounded-full bg-accent/10 blur-3xl" />
        <div className="absolute -right-28 bottom-10 h-96 w-96 rounded-full bg-purple/10 blur-3xl" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_12%,rgb(var(--accent)/0.13),transparent_34%),linear-gradient(rgb(var(--accent)/0.035)_1px,transparent_1px),linear-gradient(90deg,rgb(var(--purple)/0.03)_1px,transparent_1px)] bg-[length:100%_100%,42px_42px,42px_42px]" />
      </div>
      <div className="relative z-10 border-b border-accent/15 bg-bg/85 px-5 py-3 backdrop-blur-xl">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex h-10 w-10 items-center justify-center rounded-xl border border-accent/35 bg-accent/10 text-accent shadow-[0_0_32px_rgb(var(--accent)/0.18)]">
            <BrainCircuit size={20} />
            <span className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full bg-success shadow-[0_0_12px_rgb(var(--success))]" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-[15px] font-black tracking-[0.18em] text-heading">NEURAL ATLAS</h1>
              <span className="hidden rounded-full border border-success/35 bg-success/10 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.18em] text-success sm:inline-flex">live weave</span>
            </div>
            <p className="mt-0.5 text-[11px] text-muted">TOBI's second brain, arranged as a cortex map of memory, work, sources, and semantic links.</p>
          </div>
          <div className="ml-auto grid grid-cols-2 gap-1.5 text-[10px] sm:flex">
            <div className="rounded-lg border border-border/80 bg-bg/55 px-2.5 py-1.5">
              <div className="flex items-center gap-1 text-muted"><Orbit size={11} /> Nodes</div>
              <div className="font-mono text-sm font-semibold text-heading">{data.nodes.length}</div>
            </div>
            <div className="rounded-lg border border-border/80 bg-bg/55 px-2.5 py-1.5">
              <div className="flex items-center gap-1 text-muted"><Share2 size={11} /> Links</div>
              <div className="font-mono text-sm font-semibold text-heading">{data.edges.length}</div>
            </div>
            <div className="rounded-lg border border-border/80 bg-bg/55 px-2.5 py-1.5">
              <div className="flex items-center gap-1 text-muted"><Activity size={11} /> Density</div>
              <div className="font-mono text-sm font-semibold text-heading">{density}</div>
            </div>
            <div className="rounded-lg border border-border/80 bg-bg/55 px-2.5 py-1.5">
              <div className="flex items-center gap-1 text-muted"><RadioTower size={11} /> Sources</div>
              <div className="font-mono text-sm font-semibold text-heading">{activeSources}/{sources.length || 0}</div>
            </div>
          </div>
        </div>
      </div>

      <div ref={wrapRef} className="relative z-0 flex-1 overflow-hidden">
        {connectMode && (
          <div className="absolute left-1/2 top-32 z-20 -translate-x-1/2 rounded-full border border-purple/50 bg-purple/15 px-3 py-1 text-[11px] font-medium text-purple shadow-[0_0_28px_rgb(var(--purple)/0.22)] backdrop-blur">
            Connect mode · {connectFirst ? 'pick the second node' : 'pick the first node'}
          </div>
        )}

        <GraphToolbar
          domainCounts={domainCounts} domain={domain} onDomain={setDomain}
          layout={layout} onLayout={pickLayout} onFit={() => canvasRef.current?.zoomToFit()}
          performance={performance} onTogglePerformance={() => setPerformance(p => !p)}
          connectMode={connectMode} onToggleConnect={() => { setConnectMode(m => !m); setConnectFirst(null); setHighlightIds(new Set()) }}
          onAddNode={addNode} onRefresh={refresh} syncing={syncing}
          minWeight={minWeight} onMinWeight={setMinWeight}
          category={category} onCategory={setCategory}
          onFocusResult={focusNode}
        />

        {!empty && (
          <ForceGraphCanvas
            ref={canvasRef}
            data={data} width={dims.w} height={dims.h} layout={layout}
            performance={performance} connectMode={connectMode} highlightIds={highlightIds}
            onNodeClick={(n) => { setSelectedId(n.id); setHighlightIds(new Set()) }}
            onNodeDoubleClick={(n) => focusNode(n.id)}
            onConnectPick={onConnectPick}
            onBackgroundClick={() => { setSelectedId(null); setHighlightIds(new Set()) }}
            onPin={pin}
          />
        )}

        {!empty && <GraphLegend communities={communities} domainCounts={domainCounts} />}
        {!empty && <TimelineScrubber events={events} onScrub={setDateTo} />}

        {loading && (
          <div className="absolute inset-0 z-20 flex items-center justify-center">
            <div className="relative overflow-hidden rounded-2xl border border-accent/25 bg-bg/85 px-5 py-4 text-sm text-muted shadow-[0_0_54px_rgb(var(--accent)/0.16)] backdrop-blur-xl">
              <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/70 to-transparent" />
              <div className="flex items-center gap-3">
                <RefreshCw size={16} className="animate-spin text-accent" />
                <div>
                  <div className="font-semibold text-heading">Weaving neural topology</div>
                  <div className="text-[11px] text-muted">Clustering memories, tasks, projects, and source mirrors...</div>
                </div>
              </div>
            </div>
          </div>
        )}

        {empty && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl border border-accent/35 bg-accent/10 text-accent shadow-[0_0_44px_rgb(var(--accent)/0.18)]">
              <Cpu size={28} />
            </div>
            <div className="text-sm font-semibold text-text">No neural map loaded.</div>
            <div className="max-w-xs text-xs text-muted">Sync to weave memories, tasks, projects and connected sources into one neuron map.</div>
            <button onClick={refresh} disabled={syncing}
              className="mt-1 flex items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-4 py-2 text-xs font-semibold text-accent shadow-[0_0_24px_rgb(var(--accent)/0.12)] hover:bg-accent/20 disabled:opacity-50">
              <RefreshCw size={13} className={syncing ? 'animate-spin' : ''} /> Sync now
            </button>
          </div>
        )}

        <NodeDetailPanel
          nodeId={selectedId}
          onClose={() => setSelectedId(null)}
          onChanged={load}
          onFocusNode={focusNode}
        />
      </div>
    </div>
  )
}

function summarize(res: Record<string, unknown>): string {
  const parts: string[] = []
  const internal = res.internal as Record<string, number> | undefined
  if (internal) parts.push(`${(internal.memory || 0) + (internal.task || 0) + (internal.project || 0)} internal`)
  if (typeof res.semantic_edges === 'number') parts.push(`${res.semantic_edges} semantic links`)
  return parts.join(' · ') || 'done'
}

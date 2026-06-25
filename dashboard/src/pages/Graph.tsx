import { useEffect, useRef, useState, useCallback } from 'react'
import { Share2, RefreshCw } from 'lucide-react'
import {
  getGraph, getGraphSources, getGraphTimeline, getGraphCommunities, syncGraph, createGraphNode,
  createGraphEdge, saveGraphLayout,
  type GraphData, type GraphNode, type GraphSource, type TimelineEvent, type GraphCommunity,
} from '../api'
import { useToast } from '../context/ToastProvider'
import ForceGraphCanvas, { type CanvasHandle } from '../components/graph/ForceGraphCanvas'
import NodeDetailPanel from '../components/graph/NodeDetailPanel'
import GraphToolbar from '../components/graph/GraphToolbar'
import GraphLegend from '../components/graph/GraphLegend'
import TimelineScrubber from '../components/graph/TimelineScrubber'

const EMPTY: GraphData = { nodes: [], edges: [] }

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

  // ui state
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

  const pin = useCallback((n: any) => {
    saveGraphLayout([{ id: n.id, x: n.x, y: n.y, pinned: true }]).catch(() => {})
  }, [])

  const empty = !loading && data.nodes.length === 0

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2.5 border-b border-border px-5 py-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-accent/30 bg-accent/10 text-accent"><Share2 size={16} /></div>
        <div>
          <h1 className="text-sm font-bold text-heading">Graph</h1>
          <p className="text-[11px] text-muted">Your second brain — memories, tasks, projects & sources, connected</p>
        </div>
        <div className="ml-auto text-[11px] text-muted">{data.nodes.length} nodes · {data.edges.length} links</div>
      </div>

      <div ref={wrapRef} className="relative flex-1 overflow-hidden grid-bg">
        {connectMode && (
          <div className="absolute left-1/2 top-14 z-20 -translate-x-1/2 rounded-full border border-purple/50 bg-purple/15 px-3 py-1 text-[11px] text-purple">
            Connect mode · {connectFirst ? 'pick the second node' : 'pick the first node'}
          </div>
        )}

        <GraphToolbar
          sources={sources} domain={domain} onDomain={setDomain}
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
            data={data} width={dims.w} height={dims.h}
            performance={performance} connectMode={connectMode} highlightIds={highlightIds}
            onNodeClick={(n) => { setSelectedId(n.id); setHighlightIds(new Set()) }}
            onNodeDoubleClick={(n) => focusNode(n.id)}
            onConnectPick={onConnectPick}
            onBackgroundClick={() => { setSelectedId(null); setHighlightIds(new Set()) }}
            onPin={pin}
          />
        )}

        {!empty && <GraphLegend communities={communities} />}
        {!empty && <TimelineScrubber events={events} onScrub={setDateTo} />}

        {loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center">
            <div className="flex items-center gap-2 rounded-lg border border-border bg-surface/80 px-4 py-2 text-sm text-muted backdrop-blur">
              <RefreshCw size={14} className="animate-spin text-accent" /> Weaving the graph…
            </div>
          </div>
        )}

        {empty && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-accent/30 bg-accent/10 text-accent">
              <Share2 size={26} />
            </div>
            <div className="text-sm text-text">Your graph is empty.</div>
            <div className="max-w-xs text-xs text-muted">Sync to weave memories, tasks, projects and connected sources into one neuron map.</div>
            <button onClick={refresh} disabled={syncing}
              className="mt-1 flex items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-4 py-2 text-xs font-semibold text-accent hover:bg-accent/20 disabled:opacity-50">
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

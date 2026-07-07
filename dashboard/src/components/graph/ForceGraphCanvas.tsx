import { useRef, useEffect, useMemo, useCallback, useImperativeHandle, forwardRef } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import { forceCollide, forceRadial, forceX, forceY } from 'd3-force'
import type { GraphData, GraphNode, GraphEdge } from '../../api'

/* The single isolated renderer for the knowledge graph. All canvas/force-graph logic
 * lives here so the library can be swapped (Sigma/Cosmograph) if scale ever demands it,
 * without touching the page. Glow via shadowBlur, cluster hulls via onRenderFramePre,
 * "synapse" flow via directional particles, hover→highlight-neighbours, drag→pin. */

const EDGE_COLOR: Record<string, string> = {
  ref:      'rgba(88,166,255,',
  semantic: 'rgba(167,139,250,',
  tag:      'rgba(45,212,191,',
  manual:   'rgba(244,114,182,',
}

const DOMAIN_ANCHOR: Record<string, number> = {
  memory: -2.72,
  project: -1.85,
  task: -0.92,
  github: -0.08,
  notion: 0.72,
  gdrive: 1.42,
  local: 2.18,
  manual: 2.82,
}

const seeded = (v: number) => {
  const x = Math.sin(v * 12.9898) * 43758.5453
  return x - Math.floor(x)
}

const brainPoint = (angle: number, radius: number) => {
  const wave = 1 + Math.sin(angle * 3.1) * 0.08 + Math.cos(angle * 5.3) * 0.05
  const side = Math.sign(Math.cos(angle)) || 1
  return {
    x: Math.cos(angle) * radius * 1.18 * wave + side * 24,
    y: Math.sin(angle) * radius * 0.82 * wave + Math.sin(angle * 2) * 18,
  }
}

/** Node radius from degree — shared by drawing, hit-testing, and collision. */
function nodeRadius(node: any): number {
  const deg = node.degree || 0
  return Math.max(3.5, Math.min(18, 3.5 + Math.sqrt(deg) * 2.1))
}

/** Custom d3 force: pull each node toward its community centroid → tight, separated
 *  clusters without needing dense edges (the anti-hairball trick from the research). */
function makeClusterForce(strength = 0.14) {
  let nodes: any[] = []
  const force = (alpha: number) => {
    const cent: Record<string, { x: number; y: number; n: number }> = {}
    for (const n of nodes) {
      const c = String(n.community ?? -1)
      if (!cent[c]) cent[c] = { x: 0, y: 0, n: 0 }
      cent[c].x += n.x; cent[c].y += n.y; cent[c].n++
    }
    for (const c in cent) { cent[c].x /= cent[c].n; cent[c].y /= cent[c].n }
    const s = strength * alpha
    for (const n of nodes) {
      const c = cent[String(n.community ?? -1)]
      if (!c) continue
      n.vx += (c.x - n.x) * s
      n.vy += (c.y - n.y) * s
    }
  }
  ;(force as any).initialize = (n: any[]) => { nodes = n }
  return force
}

function makeBrainForce(strength = 0.05) {
  let nodes: any[] = []
  const force = (alpha: number) => {
    const s = strength * alpha
    for (const n of nodes) {
      const deg = Math.max(0, n.degree || 0)
      const hubPull = Math.min(0.55, Math.sqrt(deg) * 0.035)
      const target = brainPoint(n.__angle || 0, (n.__radius || 300) * (1 - hubPull))
      n.vx += (target.x - n.x) * s
      n.vy += (target.y - n.y) * s
    }
  }
  ;(force as any).initialize = (n: any[]) => { nodes = n }
  return force
}

/** Convex hull (Andrew's monotone chain) for clean cluster outlines. */
function convexHull(pts: { x: number; y: number }[]): { x: number; y: number }[] {
  if (pts.length < 3) return pts
  const p = pts.slice().sort((a, b) => a.x - b.x || a.y - b.y)
  const cross = (o: any, a: any, b: any) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x)
  const lower: any[] = []
  for (const q of p) { while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], q) <= 0) lower.pop(); lower.push(q) }
  const upper: any[] = []
  for (let i = p.length - 1; i >= 0; i--) { const q = p[i]; while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], q) <= 0) upper.pop(); upper.push(q) }
  lower.pop(); upper.pop()
  return lower.concat(upper)
}

export type CanvasHandle = {
  focusNode: (id: number) => void
  zoomToFit: () => void
}

type Props = {
  data: GraphData
  width: number
  height: number
  performance: boolean
  connectMode: boolean
  highlightIds: Set<number>
  onNodeClick: (n: GraphNode) => void
  onNodeDoubleClick: (n: GraphNode) => void
  onConnectPick: (n: GraphNode) => void
  onBackgroundClick: () => void
  onPin: (n: GraphNode) => void
}

const ForceGraphCanvas = forwardRef<CanvasHandle, Props>(function ForceGraphCanvas(
  { data, width, height, performance, connectMode, highlightIds, onNodeClick, onNodeDoubleClick, onConnectPick, onBackgroundClick, onPin }, ref,
) {
  const fgRef = useRef<any>(null)
  const hoverRef = useRef<number | null>(null)
  const neighborRef = useRef<Set<number>>(new Set())
  const linkNeighborRef = useRef<Set<string>>(new Set())

  // Map our {nodes, edges} → force-graph {nodes, links}. Seed each node near its
  // community's slot on a ring so clusters start separated (research: pre-placing nodes
  // prevents the everything-collapses-to-one-ball hairball). Pinned nodes stay fixed.
  const graphData = useMemo(() => {
    const comms = Array.from(new Set(data.nodes.map(n => n.community ?? -1)))
    const slot = new Map(comms.map((c, i) => [c, i]))
    const grouped = new Map<string, number>()
    const R = Math.max(220, Math.min(620, 160 + Math.sqrt(Math.max(1, data.nodes.length)) * 34))
    const nodes = data.nodes.map(n => {
      const o: any = { ...n }
      if (n.pinned && n.x != null && n.y != null) { o.fx = n.x; o.fy = n.y }
      else {
        const community = String(n.community ?? n.domain ?? -1)
        const order = grouped.get(community) || 0
        grouped.set(community, order + 1)
        const base = DOMAIN_ANCHOR[n.domain] ?? (((slot.get(n.community ?? -1) ?? 0) / Math.max(1, comms.length)) * 2 * Math.PI - Math.PI)
        const local = order * 2.399963 + seeded(n.id) * 0.7
        const ring = Math.sqrt(order + 1) * (10 + seeded(n.id + 11) * 8)
        const angle = base + (seeded(n.id + 7) - 0.5) * 0.42
        const anchor = brainPoint(angle, R * (0.48 + seeded(n.id + 19) * 0.22))
        o.__angle = angle
        o.__radius = R * (0.55 + seeded(n.id + 31) * 0.28)
        o.x = anchor.x + Math.cos(local) * ring
        o.y = anchor.y + Math.sin(local) * ring
      }
      return o
    })
    return { nodes, links: data.edges.map(e => ({ ...e, source: e.source, target: e.target })) }
  }, [data])

  // adjacency for hover-highlight
  const adjacency = useMemo(() => {
    const m = new Map<number, Set<number>>()
    for (const e of data.edges) {
      if (!m.has(e.source)) m.set(e.source, new Set())
      if (!m.has(e.target)) m.set(e.target, new Set())
      m.get(e.source)!.add(e.target)
      m.get(e.target)!.add(e.source)
    }
    return m
  }, [data.edges])

  useImperativeHandle(ref, () => ({
    focusNode(id: number) {
      const node: any = graphData.nodes.find((n: any) => n.id === id)
      if (node && fgRef.current && node.x != null) {
        fgRef.current.centerAt(node.x, node.y, 800)
        fgRef.current.zoom(4, 800)
      }
    },
    zoomToFit() { fgRef.current?.zoomToFit(500, 60) },
  }), [graphData])

  // forceAtlas2-style layout (mirrors graphify): strong repulsion, long links, collision
  // to avoid overlap, very weak pull to centre so communities spread into clean clusters.
  useEffect(() => {
    const fg = fgRef.current
    if (!fg) return
    fg.d3Force('charge')?.strength(performance ? -95 : -175).distanceMax(900)
    const link = fg.d3Force('link')
    // weak links: the cluster force (below) does the grouping, so edges don't collapse
    // everything into one ball — they just hint structure.
    if (link) link.distance((l: any) => 64 + (1 - Math.min(1, l.weight || 0.4)) * 84).strength(0.022)
    fg.d3Force('center', null)
    fg.d3Force('x', forceX(0).strength(0.018))
    fg.d3Force('y', forceY(0).strength(0.018))
    fg.d3Force('radial', forceRadial((n: any) => n.__radius || 260, 0, 0).strength(0.025))
    fg.d3Force('brain', makeBrainForce(performance ? 0.035 : 0.055))
    fg.d3Force('collide', forceCollide((n: any) => nodeRadius(n) + 8).strength(0.95).iterations(2))
    fg.d3Force('cluster', makeClusterForce(performance ? 0.12 : 0.18))
    fg.d3ReheatSimulation?.()
  }, [performance])

  // Gentle one-time fit + freeze physics once the engine settles (graphify does this too).
  const onEngineStop = useCallback(() => {
    fgRef.current?.zoomToFit(600, 70)
  }, [])

  const setHover = useCallback((node: any) => {
    hoverRef.current = node ? node.id : null
    const nb = new Set<number>()
    const lk = new Set<string>()
    if (node) {
      nb.add(node.id)
      const adj = adjacency.get(node.id)
      if (adj) for (const id of adj) { nb.add(id); lk.add([node.id, id].sort().join('-')) }
    }
    neighborRef.current = nb
    linkNeighborRef.current = lk
  }, [adjacency])

  const nodeCanvasObject = useCallback((node: any, ctx: CanvasRenderingContext2D, scale: number) => {
    const r = nodeRadius(node)
    const color = node.color || '#58a6ff'
    const hovering = hoverRef.current != null
    const isFocus = highlightIds.has(node.id)
    const dim = (hovering && !neighborRef.current.has(node.id)) || (highlightIds.size > 0 && !isFocus)
    ctx.globalAlpha = dim ? 0.18 : 1

    if (!performance) {
      const pulse = 1 + Math.sin(Date.now() / 900 + node.id) * 0.08
      ctx.shadowColor = color
      ctx.shadowBlur = (isFocus ? 26 : 12) + r
      ctx.beginPath()
      ctx.arc(node.x, node.y, r * (2.1 + pulse), 0, 2 * Math.PI)
      ctx.fillStyle = color.replace(')', ',0.08)')
      ctx.globalAlpha = dim ? 0.04 : 0.12
      ctx.fill()
      ctx.globalAlpha = dim ? 0.18 : 1
      ctx.shadowColor = color
      ctx.shadowBlur = (isFocus ? 24 : 14) + r
    }
    ctx.beginPath()
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
    ctx.fillStyle = color
    ctx.fill()
    ctx.shadowBlur = 0
    // bright core
    ctx.beginPath()
    ctx.arc(node.x, node.y, r * 0.45, 0, 2 * Math.PI)
    ctx.fillStyle = 'rgba(244,252,255,0.88)'
    ctx.fill()
    if (!performance && r > 7) {
      ctx.beginPath()
      ctx.arc(node.x - r * 0.18, node.y - r * 0.2, r * 0.18, 0, 2 * Math.PI)
      ctx.fillStyle = 'rgba(34,211,238,0.9)'
      ctx.fill()
    }
    if (isFocus) {
      ctx.strokeStyle = '#ffffff'
      ctx.lineWidth = 1.5 / scale
      ctx.beginPath(); ctx.arc(node.x, node.y, r + 3, 0, 2 * Math.PI); ctx.stroke()
    }
    // label only when zoomed in enough (level-of-detail)
    if (scale > 1.4 && !dim) {
      const label = String(node.title || '').slice(0, 24)
      ctx.font = `600 ${Math.max(3, 4.5)}px ui-sans-serif, system-ui`
      ctx.fillStyle = 'rgba(230,248,255,0.9)'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'top'
      ctx.fillText(label, node.x, node.y + r + 2)
    }
    ctx.globalAlpha = 1
  }, [performance, highlightIds])

  const nodePointerAreaPaint = useCallback((node: any, color: string, ctx: CanvasRenderingContext2D) => {
    ctx.fillStyle = color
    ctx.beginPath(); ctx.arc(node.x, node.y, nodeRadius(node) + 4, 0, 2 * Math.PI); ctx.fill()
  }, [])

  // Glowing community hulls (graphify technique): per community, a real convex hull
  // around member positions, expanded from the centroid, filled translucent + stroked,
  // with the community label floated above. Drawn behind nodes via onRenderFramePre.
  const onRenderFramePre = useCallback((ctx: CanvasRenderingContext2D, globalScale: number) => {
    if (!performance) {
      const t = Date.now() / 4200
      ctx.save()
      ctx.globalCompositeOperation = 'lighter'
      ctx.translate(0, 0)
      const rings = [180, 300, 430, 560]
      for (let i = 0; i < rings.length; i++) {
        ctx.beginPath()
        ctx.ellipse(0, 0, rings[i] * 1.22, rings[i] * 0.84, Math.sin(t + i) * 0.02, 0, 2 * Math.PI)
        ctx.strokeStyle = `rgba(88,166,255,${0.08 - i * 0.012})`
        ctx.lineWidth = 1.2 / globalScale
        ctx.stroke()
      }
      for (let i = 0; i < 4; i++) {
        const a = t + i * Math.PI * 0.5
        ctx.beginPath()
        ctx.arc(0, 0, 255 + i * 64, a, a + 0.52)
        ctx.strokeStyle = i % 2 ? 'rgba(45,212,191,0.18)' : 'rgba(244,114,182,0.14)'
        ctx.lineWidth = 2.2 / globalScale
        ctx.stroke()
      }
      ctx.beginPath()
      ctx.moveTo(0, -520)
      ctx.bezierCurveTo(-42, -230, 56, -110, -18, 0)
      ctx.bezierCurveTo(48, 128, -42, 260, 0, 530)
      ctx.strokeStyle = 'rgba(230,248,255,0.08)'
      ctx.lineWidth = 1.5 / globalScale
      ctx.stroke()
      ctx.restore()
    }
    if (performance) return
    const groups = new Map<string, any[]>()
    for (const n of graphData.nodes as any[]) {
      if (n.x == null || n.community == null) continue
      const key = String(n.community)
      if (!groups.has(key)) groups.set(key, [])
      groups.get(key)!.push(n)
    }
    for (const [, members] of groups) {
      if (members.length < 3) continue
      let cx = 0, cy = 0
      for (const m of members) { cx += m.x; cy += m.y }
      cx /= members.length; cy /= members.length
      const hull = convexHull(members.map(m => ({ x: m.x, y: m.y })))
        .map(p => ({ x: cx + (p.x - cx) * 1.22, y: cy + (p.y - cy) * 1.22 }))
      if (hull.length < 3) continue
      const col = members[0].color || '#58a6ff'
      ctx.save()
      ctx.lineJoin = 'round'
      ctx.beginPath()
      ctx.moveTo(hull[0].x, hull[0].y)
      for (let i = 1; i < hull.length; i++) ctx.lineTo(hull[i].x, hull[i].y)
      ctx.closePath()
      ctx.shadowColor = col
      ctx.shadowBlur = 22 / globalScale
      ctx.globalAlpha = 0.075; ctx.fillStyle = col; ctx.fill()
      ctx.globalAlpha = 0.34; ctx.lineWidth = 1.5 / globalScale; ctx.strokeStyle = col; ctx.stroke()
      ctx.shadowBlur = 0
      // community label floated near the top of the hull, constant on-screen size
      let topY = Infinity, topX = cx
      for (const p of hull) if (p.y < topY) { topY = p.y; topX = p.x }
      const label = members[0].community_label || ''
      if (label && globalScale > 0.5) {
        ctx.globalAlpha = 0.7
        ctx.fillStyle = col
        ctx.font = `600 ${11 / globalScale}px ui-sans-serif, system-ui`
        ctx.textAlign = 'center'; ctx.textBaseline = 'bottom'
        ctx.fillText(String(label), cx, topY - 4 / globalScale)
      }
      ctx.restore()
    }
  }, [graphData, performance])

  const linkColor = useCallback((link: any) => {
    const base = EDGE_COLOR[link.type] || 'rgba(139,148,158,'
    const sid = typeof link.source === 'object' ? link.source.id : link.source
    const tid = typeof link.target === 'object' ? link.target.id : link.target
    const key = [sid, tid].sort().join('-')
    const hovering = hoverRef.current != null
    const on = !hovering || linkNeighborRef.current.has(key)
    return base + (on ? 0.5 : 0.06) + ')'
  }, [])

  const handleClick = useCallback((node: any) => {
    if (connectMode) onConnectPick(node)
    else onNodeClick(node)
  }, [connectMode, onConnectPick, onNodeClick])

  // re-heat layout when data identity changes so new nodes settle
  useEffect(() => { fgRef.current?.d3ReheatSimulation?.() }, [graphData])

  return (
    <ForceGraph2D
      ref={fgRef}
      width={width}
      height={height}
      graphData={graphData}
      backgroundColor="rgba(0,0,0,0)"
      nodeRelSize={4}
      nodeCanvasObject={nodeCanvasObject}
      nodePointerAreaPaint={nodePointerAreaPaint}
      onRenderFramePre={onRenderFramePre}
      linkColor={linkColor}
      linkWidth={(l: any) => Math.max(0.4, (l.weight || 1) * 1.4)}
      linkCurvature={0.12}
      linkDirectionalParticles={performance ? 0 : 2}
      linkDirectionalParticleWidth={(l: any) => (l.type === 'semantic' ? 1.6 : 1.2)}
      linkDirectionalParticleSpeed={0.006}
      onNodeHover={setHover}
      onNodeClick={handleClick}
      onNodeRightClick={(n: any) => onNodeDoubleClick(n)}
      onBackgroundClick={onBackgroundClick}
      onNodeDragEnd={(node: any) => { node.fx = node.x; node.fy = node.y; onPin(node) }}
      onEngineStop={onEngineStop}
      d3VelocityDecay={0.32}
      cooldownTicks={performance ? 90 : 220}
      warmupTicks={30}
    />
  )
})

export default ForceGraphCanvas
export type { GraphNode, GraphEdge }

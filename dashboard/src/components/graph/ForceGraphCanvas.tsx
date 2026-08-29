import { useRef, useEffect, useMemo, useCallback, useImperativeHandle, forwardRef } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import { forceCollide, forceX, forceY } from 'd3-force'
import type { GraphData, GraphNode, GraphEdge } from '../../api.graph'
import { computeLayout, nodeRadius, type LayoutMode } from './layouts'

/* The single isolated renderer for the knowledge graph. All canvas/force-graph logic lives
 * here so the library can be swapped (Sigma/Cosmograph) if scale ever demands it, without
 * touching the page.
 *
 * The layout itself lives in ./layouts.ts. Three of the four modes compute every position up
 * front and pin it, so nothing moves and the picture is identical on every load; only 'force'
 * runs physics, and it runs ONE coherent system (repulsion + real springs + collision + a weak
 * centre pull), mirroring graphify's single ForceAtlas2 pass rather than blending five forces
 * that pull each node toward three different places.
 */

const EDGE_COLOR: Record<string, string> = {
  ref: 'rgba(88,166,255,',
  semantic: 'rgba(167,139,250,',
  tag: 'rgba(45,212,191,',
  manual: 'rgba(244,114,182,',
}

/** How many of the best-connected nodes keep their label on at every zoom level. */
const ALWAYS_LABELLED = 12
/** Captions are drawn at a fixed screen size, so this only suppresses them when the whole map
 *  is zoomed far out; collision skipping handles crowding above it. */
const CAPTION_MIN_SCALE = 0.12

const seeded = (value: number) => {
  const x = Math.sin(value * 12.9898) * 43758.5453
  return x - Math.floor(x)
}

/** Custom d3 force for 'Free' mode only: a gentle pull toward each community's centroid, so
 *  clusters separate even where edges are sparse. It is the only force competing with the
 *  springs, and at 0.06 it nudges rather than overrides. */
function makeClusterForce(strength = 0.06) {
  let nodes: any[] = []
  const force = (alpha: number) => {
    const centroid: Record<string, { x: number; y: number; n: number }> = {}
    for (const node of nodes) {
      const key = String(node.community ?? -1)
      if (!centroid[key]) centroid[key] = { x: 0, y: 0, n: 0 }
      centroid[key].x += node.x; centroid[key].y += node.y; centroid[key].n++
    }
    for (const key in centroid) { centroid[key].x /= centroid[key].n; centroid[key].y /= centroid[key].n }
    const step = strength * alpha
    for (const node of nodes) {
      const target = centroid[String(node.community ?? -1)]
      if (!target) continue
      node.vx += (target.x - node.x) * step
      node.vy += (target.y - node.y) * step
    }
  }
  ;(force as any).initialize = (n: any[]) => { nodes = n }
  return force
}

/** Convex hull (Andrew's monotone chain) — only used by 'Free' mode, where node positions are
 *  emergent and there is no exact circle to draw around a community. */
function convexHull(points: { x: number; y: number }[]): { x: number; y: number }[] {
  if (points.length < 3) return points
  const sorted = points.slice().sort((a, b) => a.x - b.x || a.y - b.y)
  const cross = (o: any, a: any, b: any) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x)
  const lower: any[] = []
  for (const point of sorted) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], point) <= 0) lower.pop()
    lower.push(point)
  }
  const upper: any[] = []
  for (let i = sorted.length - 1; i >= 0; i--) {
    const point = sorted[i]
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], point) <= 0) upper.pop()
    upper.push(point)
  }
  lower.pop(); upper.pop()
  return lower.concat(upper)
}

const truncate = (text: string, max: number) =>
  text.length > max ? `${text.slice(0, max - 1)}…` : text

/* Fitting the view has to know about the panels floating over the canvas, otherwise the top
 * row of the map lands behind the toolbar — which is what zoomToFit's uniform padding did. */
const TOP_CHROME = 148   // layout switcher + hint row
const BOTTOM_CHROME = 78 // timeline scrubber
const SIDE_CHROME = 40
/** Room for the cluster/lane outlines and their captions, which sit outside the node bounds. */
const SHAPE_MARGIN = 52

type LabelBox = { x0: number; y0: number; x1: number; y1: number }
const overlaps = (a: LabelBox, b: LabelBox) =>
  a.x0 < b.x1 && a.x1 > b.x0 && a.y0 < b.y1 && a.y1 > b.y0

export type CanvasHandle = {
  focusNode: (id: number) => void
  zoomToFit: () => void
}

type Props = {
  data: GraphData
  width: number
  height: number
  layout: LayoutMode
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
  { data, width, height, layout, performance, connectMode, highlightIds,
    onNodeClick, onNodeDoubleClick, onConnectPick, onBackgroundClick, onPin }, ref,
) {
  const fgRef = useRef<any>(null)
  const hoverRef = useRef<number | null>(null)
  const neighborRef = useRef<Set<number>>(new Set())
  const linkNeighborRef = useRef<Set<string>>(new Set())
  /** Label boxes already claimed this frame, so two captions never print on top of each other.
   *  Reset in onRenderFramePre, which runs once before the nodes are drawn. */
  const labelBoxes = useRef<LabelBox[]>([])

  const placement = useMemo(() => computeLayout(layout, data), [layout, data])

  // Map our {nodes, edges} → force-graph {nodes, links}. In a computed layout every node gets
  // fx/fy, which d3 treats as immovable — so the picture is exactly what layouts.ts decided.
  // In 'Free' mode only the seed position is set (plus any position the owner pinned by hand).
  const graphData = useMemo(() => {
    const communities = Array.from(new Set(data.nodes.map(n => n.community ?? -1)))
    const slot = new Map(communities.map((c, i) => [c, i]))
    const seedRadius = Math.max(180, Math.min(560, 140 + Math.sqrt(Math.max(1, data.nodes.length)) * 30))

    const nodes = data.nodes.map(node => {
      const out: any = { ...node }
      const placed = placement.positions.get(node.id)
      if (placed) {
        out.x = placed.x; out.y = placed.y
        out.fx = placed.x; out.fy = placed.y
      } else if (node.pinned && node.x != null && node.y != null) {
        out.x = node.x; out.y = node.y; out.fx = node.x; out.fy = node.y
      } else {
        const angle = ((slot.get(node.community ?? -1) ?? 0) / Math.max(1, communities.length)) * Math.PI * 2
          + (seeded(node.id) - 0.5) * 0.5
        const spread = seedRadius * (0.55 + seeded(node.id + 19) * 0.45)
        out.x = Math.cos(angle) * spread
        out.y = Math.sin(angle) * spread
        out.fx = undefined; out.fy = undefined
      }
      return out
    })
    return { nodes, links: data.edges.map(e => ({ ...e, source: e.source, target: e.target })) }
  }, [data, placement])

  // adjacency for hover-highlight
  const adjacency = useMemo(() => {
    const map = new Map<number, Set<number>>()
    for (const edge of data.edges) {
      if (!map.has(edge.source)) map.set(edge.source, new Set())
      if (!map.has(edge.target)) map.set(edge.target, new Set())
      map.get(edge.source)!.add(edge.target)
      map.get(edge.target)!.add(edge.source)
    }
    return map
  }, [data.edges])

  /** The hubs whose names stay on screen at any zoom — without them the map is unreadable
   *  until you zoom in, which was the old behaviour and the reason nothing could be found.
   *  Columns are the exception: the grid is one node wide, so a caption cannot fit beside its
   *  node and the panel headers name the group instead. */
  const alwaysLabelled = useMemo(() => layout === 'columns' ? new Set<number>() : new Set(
    [...data.nodes].sort((a, b) => (b.degree || 0) - (a.degree || 0) || a.id - b.id)
      .slice(0, ALWAYS_LABELLED).map(n => n.id)), [data.nodes, layout])

  /** Frame the whole map inside the band the floating panels leave free. force-graph's own
   *  zoomToFit pads all four sides equally and knows nothing about the toolbar, so the top row
   *  of clusters ended up behind it. */
  const fitView = useCallback((ms = 420) => {
    const fg = fgRef.current
    if (!fg) return
    const points = (graphData.nodes as any[]).filter(n => n.x != null && n.y != null)
    if (!points.length) return
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
    for (const point of points) {
      if (point.x < minX) minX = point.x
      if (point.x > maxX) maxX = point.x
      if (point.y < minY) minY = point.y
      if (point.y > maxY) maxY = point.y
    }
    minX -= SHAPE_MARGIN; maxX += SHAPE_MARGIN; minY -= SHAPE_MARGIN; maxY += SHAPE_MARGIN
    // Ask the canvas for its own size rather than trusting React state, which can still hold
    // the mount-time default on the first fit and would frame the map far too small.
    const canvasWidth = (typeof fg.width === 'function' ? fg.width() : width) || width
    const canvasHeight = (typeof fg.height === 'function' ? fg.height() : height) || height
    const usableWidth = Math.max(120, canvasWidth - SIDE_CHROME * 2)
    const usableHeight = Math.max(120, canvasHeight - TOP_CHROME - BOTTOM_CHROME)
    const scale = Math.min(usableWidth / Math.max(1, maxX - minX), usableHeight / Math.max(1, maxY - minY), 2.5)
    // the free band's centre sits (TOP - BOTTOM)/2 pixels below the canvas centre
    const offset = (TOP_CHROME - BOTTOM_CHROME) / 2 / scale
    fg.zoom(scale, ms)
    fg.centerAt((minX + maxX) / 2, (minY + maxY) / 2 - offset, ms)
  }, [graphData, width, height])

  useImperativeHandle(ref, () => ({
    focusNode(id: number) {
      const node: any = graphData.nodes.find((n: any) => n.id === id)
      if (node && fgRef.current && node.x != null) {
        fgRef.current.centerAt(node.x, node.y, 800)
        fgRef.current.zoom(3.2, 800)
      }
    },
    zoomToFit() { fitView(500) },
  }), [graphData, fitView])

  // Physics exists only in 'Free' mode. One coherent system: strong repulsion, springs that
  // actually hold (0.32 — the old 0.022 meant edges did not affect placement at all), collision
  // so nothing overlaps, a weak centre pull, and a mild community nudge. Same shape of setup as
  // graphify's ForceAtlas2 pass (graphify-out/graph.html: gravity -60, springLength 120,
  // springConstant 0.08, avoidOverlap 0.8, stabilise then fit).
  useEffect(() => {
    const fg = fgRef.current
    if (!fg || layout !== 'free') return
    fg.d3Force('center', null)
    fg.d3Force('charge')?.strength(performance ? -150 : -250).distanceMax(700)
    const link = fg.d3Force('link')
    if (link) link.distance((l: any) => 90 + (1 - Math.min(1, l.weight || 0.4)) * 70).strength(0.32)
    fg.d3Force('x', forceX(0).strength(0.008))
    fg.d3Force('y', forceY(0).strength(0.008))
    fg.d3Force('collide', forceCollide((n: any) => nodeRadius(n) + 7).strength(0.9).iterations(2))
    fg.d3Force('cluster', makeClusterForce(0.06))
    fg.d3ReheatSimulation?.()
  }, [layout, performance, graphData])

  // Frame the new arrangement whenever the layout or the data changes. A computed layout has
  // nothing to settle, so waiting for the engine to stop would leave it off-screen.
  useEffect(() => {
    const timer = setTimeout(() => fitView(), layout === 'free' ? 900 : 60)
    return () => clearTimeout(timer)
  }, [graphData, layout, fitView])

  const onEngineStop = useCallback(() => {
    if (layout === 'free') fitView(600)
  }, [layout, fitView])

  const setHover = useCallback((node: any) => {
    const nextId = node ? node.id : null
    if (nextId === hoverRef.current) return
    hoverRef.current = nextId
    const neighbours = new Set<number>()
    const links = new Set<string>()
    if (node) {
      neighbours.add(node.id)
      for (const id of adjacency.get(node.id) || []) {
        neighbours.add(id)
        links.add([node.id, id].sort().join('-'))
      }
    }
    neighborRef.current = neighbours
    linkNeighborRef.current = links
    // particles are emitted from an accessor that is read on refresh, so ask for one
    fgRef.current?.refresh?.()
  }, [adjacency])

  const nodeCanvasObject = useCallback((node: any, ctx: CanvasRenderingContext2D, scale: number) => {
    const radius = nodeRadius(node)
    const color = node.color || '#58a6ff'
    const hovering = hoverRef.current != null
    const isFocus = highlightIds.has(node.id)
    const isNeighbour = neighborRef.current.has(node.id)
    const dim = (hovering && !isNeighbour) || (highlightIds.size > 0 && !isFocus)
    const accent = isFocus || (hovering && isNeighbour)

    ctx.globalAlpha = dim ? 0.16 : 1

    // Soft halo. No shadowBlur on the general case: it is the single most expensive canvas
    // operation and it was being applied to every node, every frame.
    if (!performance || accent) {
      ctx.globalAlpha = dim ? 0.03 : 0.11
      ctx.beginPath()
      ctx.arc(node.x, node.y, radius * 2.2, 0, 2 * Math.PI)
      ctx.fillStyle = color
      ctx.fill()
      ctx.globalAlpha = dim ? 0.16 : 1
    }
    if (accent) { ctx.shadowColor = color; ctx.shadowBlur = 18 + radius }

    ctx.beginPath()
    ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI)
    ctx.fillStyle = color
    ctx.fill()
    ctx.shadowBlur = 0

    // bright core, so a node still reads as a node against its own halo
    ctx.beginPath()
    ctx.arc(node.x, node.y, radius * 0.42, 0, 2 * Math.PI)
    ctx.fillStyle = 'rgba(244,252,255,0.88)'
    ctx.fill()

    if (isFocus) {
      ctx.strokeStyle = '#ffffff'
      ctx.lineWidth = 1.5 / scale
      ctx.beginPath(); ctx.arc(node.x, node.y, radius + 3 / scale, 0, 2 * Math.PI); ctx.stroke()
    }

    // Labels are sized in SCREEN pixels (/scale), so they stay legible at every zoom. Hubs,
    // the hovered neighbourhood and search hits are always named; the rest appear on zoom-in.
    // Nodes are painted highest-degree first, so when two captions want the same space the
    // better-connected one keeps it and the other is simply left off.
    const forced = isFocus || (hovering && isNeighbour)
    const named = forced || alwaysLabelled.has(node.id) || scale > 2
    if (named && !dim) {
      const text = truncate(String(node.title || ''), 26)
      const fontSize = 11 / scale
      ctx.font = `600 ${fontSize}px ui-sans-serif, system-ui, sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'top'
      const top = node.y + radius + 3 / scale
      const boxWidth = ctx.measureText(text).width + 6 / scale
      const box: LabelBox = {
        x0: node.x - boxWidth / 2, x1: node.x + boxWidth / 2,
        y0: top - 1 / scale, y1: top + fontSize + 3 / scale,
      }
      if (forced || !labelBoxes.current.some(other => overlaps(box, other))) {
        labelBoxes.current.push(box)
        ctx.globalAlpha = 0.72
        ctx.fillStyle = 'rgba(5,12,22,0.85)'
        ctx.fillRect(box.x0, box.y0, boxWidth, fontSize + 4 / scale)
        ctx.globalAlpha = 1
        ctx.fillStyle = accent ? '#ffffff' : 'rgba(214,238,255,0.92)'
        ctx.fillText(text, node.x, top)
      }
    }
    ctx.globalAlpha = 1
  }, [performance, highlightIds, alwaysLabelled])

  const nodePointerAreaPaint = useCallback((node: any, color: string, ctx: CanvasRenderingContext2D) => {
    ctx.fillStyle = color
    ctx.beginPath(); ctx.arc(node.x, node.y, nodeRadius(node) + 4, 0, 2 * Math.PI); ctx.fill()
  }, [])

  // The backdrop is the layout made visible, and nothing else. The previous version painted
  // concentric ellipses, four sweeping arcs and a bezier "spine" in graph coordinates — pure
  // decoration that moved with the nodes and represented no data.
  const onRenderFramePre = useCallback((ctx: CanvasRenderingContext2D, scale: number) => {
    labelBoxes.current = []

    /** A caption on its own dark plate, so it stays readable where two shapes sit close
     *  together, and reserved so no node label prints over it. */
    const label = (text: string, x: number, y: number, color: string, alpha = 0.9) => {
      const fontSize = 12 / scale
      ctx.font = `600 ${fontSize}px ui-sans-serif, system-ui, sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'bottom'
      const boxWidth = ctx.measureText(text).width + 10 / scale
      const box: LabelBox = {
        x0: x - boxWidth / 2, x1: x + boxWidth / 2,
        y0: y - fontSize - 3 / scale, y1: y + 3 / scale,
      }
      labelBoxes.current.push(box)
      ctx.globalAlpha = 0.82
      ctx.fillStyle = 'rgba(4,10,19,0.88)'
      ctx.fillRect(box.x0, box.y0, boxWidth, box.y1 - box.y0)
      ctx.globalAlpha = alpha
      ctx.fillStyle = color
      ctx.fillText(text, x, y)
      ctx.globalAlpha = 1
    }

    ctx.save()
    ctx.lineJoin = 'round'

    // Clusters mode: exact circles — we know each community's centre and radius, so these can
    // never overlap and never mislead about who belongs where.
    for (const cluster of placement.clusters) {
      ctx.beginPath()
      ctx.arc(cluster.x, cluster.y, cluster.r, 0, 2 * Math.PI)
      ctx.globalAlpha = 0.055; ctx.fillStyle = cluster.color; ctx.fill()
      ctx.globalAlpha = 0.32; ctx.lineWidth = 1.2 / scale; ctx.strokeStyle = cluster.color; ctx.stroke()
      ctx.globalAlpha = 1
      if (scale > CAPTION_MIN_SCALE) {
        label(`${truncate(cluster.label, 26)} · ${cluster.count}`,
          cluster.x, cluster.y - cluster.r - 6 / scale, cluster.color)
      }
    }

    // Orbit mode: one ring per step away from the hub.
    for (const ring of placement.rings) {
      ctx.beginPath()
      ctx.arc(0, 0, ring.r, 0, 2 * Math.PI)
      ctx.globalAlpha = 0.24; ctx.lineWidth = 1.1 / scale
      ctx.strokeStyle = 'rgba(88,166,255,1)'
      ctx.setLineDash([6 / scale, 8 / scale])
      ctx.stroke()
      ctx.setLineDash([])
      ctx.globalAlpha = 1
      if (scale > CAPTION_MIN_SCALE) label(ring.label, 0, -ring.r - 6 / scale, 'rgba(160,196,232,1)', 0.8)
    }

    // Columns mode: one panel per domain, named at the top.
    for (const lane of placement.lanes) {
      ctx.beginPath()
      const radiusCorner = 16
      ctx.moveTo(lane.x + radiusCorner, lane.y)
      ctx.arcTo(lane.x + lane.w, lane.y, lane.x + lane.w, lane.y + lane.h, radiusCorner)
      ctx.arcTo(lane.x + lane.w, lane.y + lane.h, lane.x, lane.y + lane.h, radiusCorner)
      ctx.arcTo(lane.x, lane.y + lane.h, lane.x, lane.y, radiusCorner)
      ctx.arcTo(lane.x, lane.y, lane.x + lane.w, lane.y, radiusCorner)
      ctx.closePath()
      ctx.globalAlpha = 0.05; ctx.fillStyle = lane.color; ctx.fill()
      ctx.globalAlpha = 0.28; ctx.lineWidth = 1.2 / scale; ctx.strokeStyle = lane.color; ctx.stroke()
      ctx.globalAlpha = 1
      if (scale > CAPTION_MIN_SCALE) {
        label(`${lane.label.toUpperCase()}  ·  ${lane.count}`, lane.x + lane.w / 2, lane.y - 8 / scale, lane.color)
      }
    }

    // Free mode has no computed shape, so the communities get hulls instead.
    if (placement.mode === 'free' && !performance) {
      const groups = new Map<string, any[]>()
      for (const node of graphData.nodes as any[]) {
        if (node.x == null || node.community == null) continue
        const key = String(node.community)
        if (!groups.has(key)) groups.set(key, [])
        groups.get(key)!.push(node)
      }
      for (const [, members] of groups) {
        if (members.length < 3) continue
        let cx = 0, cy = 0
        for (const member of members) { cx += member.x; cy += member.y }
        cx /= members.length; cy /= members.length
        const hull = convexHull(members.map(m => ({ x: m.x, y: m.y })))
          .map(p => ({ x: cx + (p.x - cx) * 1.16, y: cy + (p.y - cy) * 1.16 }))
        if (hull.length < 3) continue
        const color = members[0].color || '#58a6ff'
        ctx.beginPath()
        ctx.moveTo(hull[0].x, hull[0].y)
        for (let i = 1; i < hull.length; i++) ctx.lineTo(hull[i].x, hull[i].y)
        ctx.closePath()
        ctx.globalAlpha = 0.05; ctx.fillStyle = color; ctx.fill()
        ctx.globalAlpha = 0.26; ctx.lineWidth = 1.2 / scale; ctx.strokeStyle = color; ctx.stroke()
        ctx.globalAlpha = 1
        let topY = Infinity
        for (const point of hull) if (point.y < topY) topY = point.y
        const text = members[0].community_label || ''
        if (text && scale > CAPTION_MIN_SCALE) label(truncate(String(text), 26), cx, topY - 5 / scale, color)
      }
    }

    ctx.restore()
  }, [placement, graphData, performance])

  const linkKey = (link: any) => {
    const source = typeof link.source === 'object' ? link.source.id : link.source
    const target = typeof link.target === 'object' ? link.target.id : link.target
    return [source, target].sort().join('-')
  }

  const linkColor = useCallback((link: any) => {
    const base = EDGE_COLOR[link.type] || 'rgba(139,148,158,'
    const hovering = hoverRef.current != null
    const on = !hovering || linkNeighborRef.current.has(linkKey(link))
    return `${base}${on ? 0.42 : 0.05})`
  }, [])

  // Flowing particles only on the edges you are actually looking at. Running them on all 470+
  // links at once was constant motion everywhere, which is most of what made the page feel busy.
  const linkParticles = useCallback((link: any) => {
    if (performance || hoverRef.current == null) return 0
    return linkNeighborRef.current.has(linkKey(link)) ? 2 : 0
  }, [performance])

  const handleClick = useCallback((node: any) => {
    if (connectMode) onConnectPick(node)
    else onNodeClick(node)
  }, [connectMode, onConnectPick, onNodeClick])

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
      linkWidth={(l: any) => Math.max(0.4, (l.weight || 1) * 1.2)}
      linkCurvature={layout === 'free' ? 0.12 : 0.06}
      linkDirectionalParticles={linkParticles}
      linkDirectionalParticleWidth={(l: any) => (l.type === 'semantic' ? 1.6 : 1.2)}
      linkDirectionalParticleSpeed={0.006}
      onNodeHover={setHover}
      onNodeClick={handleClick}
      onNodeRightClick={(n: any) => onNodeDoubleClick(n)}
      onBackgroundClick={onBackgroundClick}
      enableNodeDrag={layout === 'free'}
      onNodeDragEnd={(node: any) => { node.fx = node.x; node.fy = node.y; onPin(node) }}
      onEngineStop={onEngineStop}
      d3VelocityDecay={0.35}
      cooldownTicks={layout === 'free' ? (performance ? 200 : 420) : 0}
      warmupTicks={layout === 'free' ? 40 : 0}
    />
  )
})

export default ForceGraphCanvas
export type { GraphNode, GraphEdge }

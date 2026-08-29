import { useEffect, useMemo, useRef, useState } from 'react'
import { computeLayout, nodeRadius, type LayoutMode } from './layouts'
import { useGraphSnapshot } from './graphSnapshot'
import { useReducedMotionPref } from '../../context/MotionProvider'
import type { GraphData } from '../../api.graph'

/* GraphSigil — the knowledge graph as a self-contained asset you can drop anywhere.
 *
 * It is the same graph and the same layout engine as the Graph page (./layouts.ts), rendered
 * to a plain canvas at whatever size the surrounding component gives it. Two properties make
 * it embeddable rather than "the Graph page, shrunk":
 *
 *  1. It sizes itself to the space. Below roughly 200px a 200-node map is mush, so the sigil
 *     keeps the best-connected nodes only, and how many it keeps scales with the pixels it has
 *     — 30-odd dots in a 48px favicon, the whole graph in a 400px panel. Positions are then
 *     normalised into the unit circle, so the arrangement fills the frame at every size.
 *  2. It follows the real graph. Data comes from the shared snapshot store, which polls while
 *     anything is watching, so when the graph grows the avatar grows with it. Nothing has to
 *     be re-exported, re-rendered, or told.
 *
 * Motion is gated on the app's motion setting; at anything below "full" the sigil draws once
 * and stays still.
 */

// ── one animation loop for every sigil on the page ────────────────────────────
type Ticker = (nowMs: number) => void
const tickers = new Set<Ticker>()
let rafId = 0
function pump(now: number) {
  for (const ticker of tickers) ticker(now)
  rafId = tickers.size ? requestAnimationFrame(pump) : 0
}
function addTicker(ticker: Ticker): () => void {
  tickers.add(ticker)
  if (!rafId) rafId = requestAnimationFrame(pump)
  return () => {
    tickers.delete(ticker)
    if (!tickers.size && rafId) { cancelAnimationFrame(rafId); rafId = 0 }
  }
}

// ── model ─────────────────────────────────────────────────────────────────────
const LINK_RGB: Record<string, string> = {
  ref: '88,166,255', semantic: '167,139,250', tag: '45,212,191', manual: '244,114,182',
}
const FALLBACK_ACCENT = '88,166,255'
const TAU = Math.PI * 2
const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(high, value))

type SigilPoint = { x: number; y: number; weight: number; color: string; hub: boolean }
type SigilLink = { ax: number; ay: number; bx: number; by: number; rgb: string; weight: number }
export type SigilModel = {
  points: SigilPoint[]
  links: SigilLink[]
  /** Normalised ring radii, so the orbit layout keeps its rings when embedded. */
  rings: number[]
  shownNodes: number
  totalNodes: number
  totalEdges: number
}

const EMPTY_MODEL: SigilModel = { points: [], links: [], rings: [], shownNodes: 0, totalNodes: 0, totalEdges: 0 }

/** How many nodes are worth drawing at this pixel size. Below ~4px of frame per node the dots
 *  merge into a smudge, so the sigil shows the best-connected slice instead of all of it. */
export function detailForSize(size: number): number {
  return Math.round(clamp(size * 0.85, 16, 260))
}

function buildModel(data: GraphData, layout: LayoutMode, maxNodes: number, fillSquare: boolean): SigilModel {
  const totals = { totalNodes: data.nodes.length, totalEdges: data.edges.length }
  if (!data.nodes.length) return { ...EMPTY_MODEL, ...totals }

  const nodes = [...data.nodes]
    .sort((a, b) => (b.degree || 0) - (a.degree || 0) || a.id - b.id)
    .slice(0, maxNodes)
  const keep = new Set(nodes.map(n => n.id))
  const edges = data.edges
    .filter(e => keep.has(e.source) && keep.has(e.target))
    .sort((a, b) => (b.weight || 0) - (a.weight || 0))
    .slice(0, Math.round(clamp(maxNodes * 4, 40, 900)))

  // 'free' is physics on the live page and has no precomputed positions; an embed has to draw
  // something the instant it mounts, so it borrows the clusters arrangement.
  const placement = computeLayout(layout === 'free' ? 'clusters' : layout, { nodes, edges })
  const positions = placement.positions
  if (!positions.size) return { ...EMPTY_MODEL, ...totals }

  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
  for (const point of positions.values()) {
    if (point.x < minX) minX = point.x
    if (point.x > maxX) maxX = point.x
    if (point.y < minY) minY = point.y
    if (point.y > maxY) maxY = point.y
  }
  const cx = (minX + maxX) / 2
  const cy = (minY + maxY) / 2

  let scale: number
  if (fillSquare) {
    scale = 1 / Math.max(1e-6, Math.max((maxX - minX) / 2, (maxY - minY) / 2))
  } else {
    // a circular frame is bounded by the furthest node from the middle, not by the bounding box
    let furthest = 0
    for (const point of positions.values()) {
      furthest = Math.max(furthest, Math.hypot(point.x - cx, point.y - cy))
    }
    scale = 1 / Math.max(1e-6, furthest)
  }

  const points: SigilPoint[] = []
  nodes.forEach((node, index) => {
    const point = positions.get(node.id)
    if (!point) return
    points.push({
      x: (point.x - cx) * scale,
      y: (point.y - cy) * scale,
      weight: nodeRadius(node) / 18,
      color: node.color || '#58a6ff',
      hub: index < 3,
    })
  })

  const links: SigilLink[] = []
  for (const edge of edges) {
    const a = positions.get(edge.source)
    const b = positions.get(edge.target)
    if (!a || !b) continue
    links.push({
      ax: (a.x - cx) * scale, ay: (a.y - cy) * scale,
      bx: (b.x - cx) * scale, by: (b.y - cy) * scale,
      rgb: LINK_RGB[edge.type] || '139,148,158',
      weight: edge.weight || 0.5,
    })
  }

  const rings = placement.rings.map(ring => ring.r * scale).filter(r => r > 0.05 && r < 1.02)
  return { points, links, rings, shownNodes: points.length, ...totals }
}

// ── drawing ───────────────────────────────────────────────────────────────────
export type SigilShape = 'circle' | 'rounded' | 'bare'

type DrawState = {
  size: number
  shape: SigilShape
  model: SigilModel
  accent: string
  animate: boolean
  showEdges: boolean
}

function drawSigil(ctx: CanvasRenderingContext2D, state: DrawState, elapsed: number) {
  const { size, shape, model, accent, animate, showEdges } = state
  const radius = size / 2
  const fill = shape === 'circle' ? 0.80 : 0.90
  const toX = (nx: number) => radius + nx * radius * fill
  const toY = (ny: number) => radius + ny * radius * fill

  ctx.clearRect(0, 0, size, size)
  ctx.save()

  if (shape === 'circle') {
    ctx.beginPath(); ctx.arc(radius, radius, radius * 0.97, 0, TAU); ctx.clip()
  } else if (shape === 'rounded') {
    const corner = size * 0.14
    ctx.beginPath()
    ctx.moveTo(corner, 0)
    ctx.arcTo(size, 0, size, size, corner)
    ctx.arcTo(size, size, 0, size, corner)
    ctx.arcTo(0, size, 0, 0, corner)
    ctx.arcTo(0, 0, size, 0, corner)
    ctx.closePath(); ctx.clip()
  }

  if (shape !== 'bare') {
    const glow = ctx.createRadialGradient(radius, radius, 0, radius, radius, radius)
    glow.addColorStop(0, `rgba(${accent},0.20)`)
    glow.addColorStop(0.62, `rgba(${accent},0.07)`)
    // Only the circle owns its own darkness — it is a framed badge. A rounded or bare sigil
    // sits on someone else's surface, so a dark stop there just paints a black tile.
    glow.addColorStop(1, shape === 'circle' ? 'rgba(4,10,19,0.55)' : `rgba(${accent},0)`)
    ctx.fillStyle = glow
    ctx.fillRect(0, 0, size, size)
  }

  // orbit rings, faint, so the layout still reads at small sizes
  ctx.lineWidth = Math.max(0.5, size * 0.0025)
  for (const ring of model.rings) {
    ctx.beginPath()
    ctx.arc(radius, radius, ring * radius * fill, 0, TAU)
    ctx.strokeStyle = `rgba(${accent},0.10)`
    ctx.stroke()
  }

  // Links fade out as the frame shrinks — in a 48px avatar the dots have to win.
  if (showEdges && model.links.length) {
    const alpha = clamp(0.08 + size / 1400, 0.08, 0.30)
    ctx.lineWidth = Math.max(0.35, size * 0.0032)
    for (const link of model.links) {
      ctx.beginPath()
      ctx.moveTo(toX(link.ax), toY(link.ay))
      ctx.lineTo(toX(link.bx), toY(link.by))
      ctx.strokeStyle = `rgba(${link.rgb},${alpha})`
      ctx.stroke()
    }
  }

  // Dot size cannot scale linearly all the way down: at 28px a proportional dot is sub-pixel
  // and the sigil renders as an empty ring. The floor keeps a tiny sigil legible.
  const unit = Math.max(1.15, size * 0.0145)
  for (const point of model.points) {
    const r = Math.max(0.9, unit * (0.55 + point.weight * 1.5))
    if (point.hub && size >= 64) {
      ctx.beginPath()
      ctx.arc(toX(point.x), toY(point.y), r * 2.8, 0, TAU)
      ctx.fillStyle = point.color
      ctx.globalAlpha = 0.16
      ctx.fill()
      ctx.globalAlpha = 1
    }
    ctx.beginPath()
    ctx.arc(toX(point.x), toY(point.y), r, 0, TAU)
    ctx.fillStyle = point.color
    ctx.fill()
    if (r > 2.2) {
      ctx.beginPath()
      ctx.arc(toX(point.x), toY(point.y), r * 0.42, 0, TAU)
      ctx.fillStyle = 'rgba(246,253,255,0.9)'
      ctx.fill()
    }
  }

  // Signal travelling along a handful of links — the thing that makes it read as a live brain
  // rather than a diagram. Picked by a fixed stride so the same links always carry a pulse.
  if (animate && model.links.length) {
    const count = Math.round(clamp(size / 38, 2, 7))
    const pulseR = Math.max(1, size * 0.011)
    for (let index = 0; index < count; index++) {
      const link = model.links[(index * 7919) % model.links.length]
      const phase = ((elapsed / 1000) * 0.32 + index / count) % 1
      const px = toX(link.ax + (link.bx - link.ax) * phase)
      const py = toY(link.ay + (link.by - link.ay) * phase)
      ctx.beginPath()
      ctx.arc(px, py, pulseR, 0, TAU)
      ctx.fillStyle = `rgba(${link.rgb},0.95)`
      ctx.fill()
    }
  }

  // Nothing in the graph yet: a slow single orbit, so the avatar is alive rather than blank.
  if (!model.points.length) {
    const angle = animate ? (elapsed / 1000) * 0.6 : 0.8
    ctx.beginPath()
    ctx.arc(radius + Math.cos(angle) * radius * 0.42, radius + Math.sin(angle) * radius * 0.42,
      Math.max(1.5, size * 0.022), 0, TAU)
    ctx.fillStyle = `rgba(${accent},0.75)`
    ctx.fill()
  }

  ctx.restore()

  if (shape === 'rounded') {
    const corner = size * 0.14
    const inset = Math.max(0.5, size * 0.006)
    ctx.beginPath()
    ctx.moveTo(corner, inset)
    ctx.arcTo(size - inset, inset, size - inset, size - inset, corner)
    ctx.arcTo(size - inset, size - inset, inset, size - inset, corner)
    ctx.arcTo(inset, size - inset, inset, inset, corner)
    ctx.arcTo(inset, inset, size - inset, inset, corner)
    ctx.closePath()
    ctx.strokeStyle = `rgba(${accent},0.26)`
    ctx.lineWidth = Math.max(0.75, size * 0.008)
    ctx.stroke()
  }

  if (shape === 'circle') {
    const border = Math.max(1, size * 0.011)
    ctx.beginPath()
    ctx.arc(radius, radius, radius - border / 2, 0, TAU)
    ctx.strokeStyle = `rgba(${accent},0.42)`
    ctx.lineWidth = border
    ctx.stroke()

    ctx.beginPath()
    ctx.arc(radius, radius, radius * 0.88, 0, TAU)
    ctx.strokeStyle = `rgba(${accent},0.14)`
    ctx.lineWidth = Math.max(0.5, size * 0.004)
    ctx.stroke()

    if (animate) {
      const start = ((elapsed / 1000) * 0.55) % TAU
      ctx.beginPath()
      ctx.arc(radius, radius, radius - border / 2, start, start + 0.85)
      ctx.strokeStyle = `rgba(${accent},0.95)`
      ctx.lineWidth = border
      ctx.lineCap = 'round'
      ctx.stroke()
      ctx.lineCap = 'butt'
    }
  }
}

// ── component ─────────────────────────────────────────────────────────────────
export type GraphSigilProps = {
  /** Rendered size in CSS pixels; the sigil is always square. */
  size?: number
  /** Which arrangement to use — the same four the Graph page offers. */
  layout?: LayoutMode
  shape?: SigilShape
  /** How many nodes to draw. 'auto' scales it to `size`, which is what you almost always want. */
  detail?: number | 'auto'
  /** Off by default only when the app's motion setting is below "full". */
  animate?: boolean
  showEdges?: boolean
  /** Draw this graph instead of the live one — for fixtures and previews. */
  data?: GraphData
  className?: string
  /** Accessible name. Defaults to a description of what the picture shows. */
  label?: string
}

export default function GraphSigil({
  size = 128, layout = 'orbit', shape = 'circle', detail = 'auto',
  animate = true, showEdges = true, data, className = '', label,
}: GraphSigilProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const live = useGraphSnapshot()
  const motion = useReducedMotionPref()
  const [accent, setAccent] = useState(FALLBACK_ACCENT)
  const [visible, setVisible] = useState(true)

  const source = data ?? live.data
  const maxNodes = detail === 'auto' ? detailForSize(size) : detail
  const model = useMemo(
    () => buildModel(source, layout, maxNodes, shape !== 'circle'),
    [source, layout, maxNodes, shape],
  )

  const moving = animate && motion === 'full' && visible

  // Theme colours live in CSS custom properties, so read them from the document and re-read
  // when the theme attribute changes — otherwise the sigil keeps the old palette after a switch.
  useEffect(() => {
    const read = () => {
      const raw = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()
      setAccent(raw ? raw.split(/[\s,]+/).slice(0, 3).join(',') : FALLBACK_ACCENT)
    }
    read()
    const observer = new MutationObserver(read)
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'class'] })
    return () => observer.disconnect()
  }, [])

  // An avatar scrolled out of view should not be burning frames.
  useEffect(() => {
    const element = wrapRef.current
    if (!element || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver(entries => setVisible(entries[0]?.isIntersecting ?? true))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  const stateRef = useRef<DrawState>({ size, shape, model, accent, animate: moving, showEdges })
  stateRef.current = { size, shape, model, accent, animate: moving, showEdges }

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ratio = Math.min(2, window.devicePixelRatio || 1)
    canvas.width = Math.round(size * ratio)
    canvas.height = Math.round(size * ratio)
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0)

    const started = performance.now()
    drawSigil(ctx, stateRef.current, 0)
    if (!moving) return
    return addTicker(now => drawSigil(ctx, stateRef.current, now - started))
  }, [size, shape, model, accent, showEdges, moving])

  const described = label ?? (model.totalNodes
    ? `TOBI knowledge graph — ${model.totalNodes} nodes, ${model.totalEdges} links`
    : 'TOBI knowledge graph — nothing connected yet')

  return (
    <div ref={wrapRef} role="img" aria-label={described} title={described}
      className={`relative shrink-0 ${className}`} style={{ width: size, height: size }}>
      <canvas ref={canvasRef} style={{ width: size, height: size, display: 'block' }} />
    </div>
  )
}

/* Deterministic layouts for the knowledge graph.
 *
 * Why this file exists: the canvas used to run five positional forces at once — a centre
 * pull, a per-node radial ring, a lobed "brain" curve, a community centroid pull, and links
 * at strength 0.022 — so every node was being dragged toward three different targets and the
 * edges (the actual data) had no say. The result had no organising principle and read as
 * noise. Every mature graph tool does the opposite: ONE layout algorithm, picked by the
 * reader, run to convergence, then frozen (Neo4j Bloom's layout menu, LangGraph/React Flow's
 * dagre-or-ELK pass, graphify's single ForceAtlas2 pass in graphify-out/graph.html).
 *
 * So: three fully computed layouts that place every node exactly once, plus one honest force
 * layout for hand-arranging. At ~200 nodes all three compute in well under a frame, which is
 * why none of them needs physics at all.
 */
import { packSiblings } from 'd3-hierarchy'
import type { GraphData, GraphNode } from '../../api.graph'

/** Ids match the labels the reader sees, so "the orbit layout" means the same thing in the
 *  UI, in this file, and in anything that embeds a layout (see GraphSigil). */
export type LayoutMode = 'clusters' | 'orbit' | 'columns' | 'free'

export const DEFAULT_LAYOUT: LayoutMode = 'clusters'

export type LayoutMeta = {
  id: LayoutMode
  label: string
  /** One plain sentence — shown as the button tooltip and as the toolbar hint. */
  hint: string
  /** Computed layouts place every node deliberately, so nudging one says nothing: drag off. */
  draggable: boolean
}

export const LAYOUTS: LayoutMeta[] = [
  { id: 'clusters', label: 'Clusters', draggable: false,
    hint: 'Each group of related nodes gets its own circle, sized by how many nodes are in it.' },
  { id: 'orbit', label: 'Orbit', draggable: false,
    hint: 'Your most connected node sits in the middle; each ring is one step further away from it.' },
  { id: 'columns', label: 'Columns', draggable: false,
    hint: 'One column per kind of thing — memories, tasks, projects, resources — most connected at the top.' },
  { id: 'free', label: 'Free', draggable: true,
    hint: 'Physics arranges it and you can drag nodes anywhere; where you drop them is remembered.' },
]

export type Placed = { x: number; y: number }

/** A community drawn as a real circle — we know its exact centre and radius, so the outline
 *  is guaranteed not to overlap its neighbours (unlike the expanded convex hulls before). */
export type ClusterShape = { key: number; x: number; y: number; r: number; color: string; label: string; count: number }
export type LaneShape = { key: string; label: string; x: number; y: number; w: number; h: number; color: string; count: number }
export type RingShape = { r: number; label: string }

export type LayoutResult = {
  mode: LayoutMode
  /** Empty for 'force' — there the simulation owns the positions. */
  positions: Map<number, Placed>
  clusters: ClusterShape[]
  lanes: LaneShape[]
  rings: RingShape[]
  hubId: number | null
}

// ── shared sizing ─────────────────────────────────────────────────────────────
const NODE_MIN_R = 3.5
const NODE_MAX_R = 18

/** Node radius from degree — shared by drawing, hit-testing, collision, and every layout,
 *  so spacing is always computed from the size a node will actually be painted at. */
export function nodeRadius(node: { degree?: number | null }): number {
  const degree = node.degree || 0
  return Math.max(NODE_MIN_R, Math.min(NODE_MAX_R, NODE_MIN_R + Math.sqrt(degree) * 2.1))
}

export const DOMAIN_COLOR: Record<string, string> = {
  memory: '#a78bfa',
  task: '#58a6ff',
  project: '#22d3ee',
  resource: '#f59e0b',
  manual: '#f472b6',
  local: '#fbbf24',
  notion: '#e5e7eb',
  github: '#8b949e',
  gdrive: '#34d399',
  internal: '#94a3b8',
}

/** Preferred left-to-right order for the domains TOBI actually produces; anything new falls
 *  in after these, biggest first, so a brand-new domain still gets a lane instead of vanishing. */
const DOMAIN_ORDER_HINT = ['memory', 'task', 'project', 'resource', 'manual', 'local', 'notion', 'github', 'gdrive']

export function domainColor(domain: string): string {
  return DOMAIN_COLOR[domain] || '#8b949e'
}

export function orderDomains(domains: string[], countOf: (d: string) => number): string[] {
  return [...domains].sort((a, b) => {
    const ia = DOMAIN_ORDER_HINT.indexOf(a)
    const ib = DOMAIN_ORDER_HINT.indexOf(b)
    if (ia !== ib) return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib)
    return countOf(b) - countOf(a) || a.localeCompare(b)
  })
}

const EMPTY_RESULT = (mode: LayoutMode): LayoutResult =>
  ({ mode, positions: new Map(), clusters: [], lanes: [], rings: [], hubId: null })

// ── entry point ───────────────────────────────────────────────────────────────
export function computeLayout(mode: LayoutMode, data: GraphData): LayoutResult {
  if (mode === 'free' || data.nodes.length === 0) return EMPTY_RESULT(mode)
  if (mode === 'clusters') return layoutClusters(data)
  if (mode === 'orbit') return layoutOrbit(data)
  return layoutColumns(data)
}

// ── 1. Cluster orbit ──────────────────────────────────────────────────────────
/** Breathing room between community discs — also the strip the disc's caption sits in. */
const CLUSTER_GAP = 46

/** Fill one disc with concentric rings, the highest-degree member dead centre. Ring k holds
 *  floor(2πk) nodes, which is exactly as many as fit at one node-step apart — so the disc is
 *  dense without overlap, and its radius falls out of the member count. */
function packDisc(members: GraphNode[], step: number): { local: Map<number, Placed>; r: number } {
  const local = new Map<number, Placed>()
  if (members.length === 0) return { local, r: step }
  local.set(members[0].id, { x: 0, y: 0 })
  let index = 1
  let ring = 1
  while (index < members.length) {
    const capacity = Math.max(1, Math.floor(2 * Math.PI * ring))
    const take = Math.min(capacity, members.length - index)
    for (let i = 0; i < take; i++) {
      // stagger each ring so nodes don't line up into spokes
      const angle = (i / take) * Math.PI * 2 + ring * 0.618
      local.set(members[index + i].id, { x: Math.cos(angle) * ring * step, y: Math.sin(angle) * ring * step })
    }
    index += take
    ring++
  }
  return { local, r: (ring - 1) * step + step * 0.8 }
}

function layoutClusters(data: GraphData): LayoutResult {
  const byCommunity = new Map<number, GraphNode[]>()
  for (const node of data.nodes) {
    const key = node.community ?? -1
    if (!byCommunity.has(key)) byCommunity.set(key, [])
    byCommunity.get(key)!.push(node)
  }

  const groups = [...byCommunity.entries()].map(([key, members]) => {
    const sorted = [...members].sort((a, b) => (b.degree || 0) - (a.degree || 0) || a.id - b.id)
    const step = 22 + nodeRadius(sorted[0]) * 0.6
    const { local, r } = packDisc(sorted, step)
    return { key, hub: sorted[0], count: sorted.length, local, r }
  })
  // biggest first is what makes packSiblings produce the tight, centred arrangement
  groups.sort((a, b) => b.r - a.r || a.key - b.key)

  const packed = packSiblings(groups.map(g => ({ r: g.r + CLUSTER_GAP })))

  const positions = new Map<number, Placed>()
  const clusters: ClusterShape[] = []
  groups.forEach((group, index) => {
    const centre = packed[index]
    for (const [id, point] of group.local) {
      positions.set(id, { x: centre.x + point.x, y: centre.y + point.y })
    }
    clusters.push({
      key: group.key,
      x: centre.x, y: centre.y, r: group.r,
      color: group.hub.color || domainColor(group.hub.domain),
      label: group.hub.community_label || group.hub.title || `Group ${group.key}`,
      count: group.count,
    })
  })

  const shift = recentre(positions)
  for (const cluster of clusters) { cluster.x += shift.x; cluster.y += shift.y }
  return { mode: 'clusters', positions, clusters, lanes: [], rings: [], hubId: groups[0]?.hub.id ?? null }
}

// ── 2. Radial hub ─────────────────────────────────────────────────────────────
const RING_MIN_GAP = 115
/** Arc length each node needs on its ring, so a crowded ring pushes itself outward. */
const RING_ARC_PER_NODE = 6

function layoutOrbit(data: GraphData): LayoutResult {
  const adjacency = new Map<number, number[]>()
  for (const node of data.nodes) adjacency.set(node.id, [])
  for (const edge of data.edges) {
    adjacency.get(edge.source)?.push(edge.target)
    adjacency.get(edge.target)?.push(edge.source)
  }

  const hub = [...data.nodes].sort((a, b) => (b.degree || 0) - (a.degree || 0) || a.id - b.id)[0]
  const byId = new Map(data.nodes.map(n => [n.id, n]))

  // breadth-first from the hub → "how many steps away is this?"
  const level = new Map<number, number>([[hub.id, 0]])
  let frontier = [hub.id]
  while (frontier.length) {
    const next: number[] = []
    for (const id of frontier) {
      for (const neighbour of adjacency.get(id) || []) {
        if (level.has(neighbour)) continue
        level.set(neighbour, (level.get(id) || 0) + 1)
        next.push(neighbour)
      }
    }
    frontier = next
  }
  const reachedMax = Math.max(0, ...level.values())
  const orphanLevel = reachedMax + 1
  for (const node of data.nodes) if (!level.has(node.id)) level.set(node.id, orphanLevel)

  const byLevel = new Map<number, GraphNode[]>()
  for (const [id, depth] of level) {
    const node = byId.get(id)
    if (!node) continue
    if (!byLevel.has(depth)) byLevel.set(depth, [])
    byLevel.get(depth)!.push(node)
  }

  const positions = new Map<number, Placed>()
  const rings: RingShape[] = []
  let radius = 0
  for (const depth of [...byLevel.keys()].sort((a, b) => a - b)) {
    const members = byLevel.get(depth)!
    if (depth === 0) { positions.set(members[0].id, { x: 0, y: 0 }); continue }
    radius = Math.max(radius + RING_MIN_GAP, members.length * RING_ARC_PER_NODE)
    // same community sits together on the arc, so the ring reads as blocks not confetti
    members.sort((a, b) => (a.community ?? -1) - (b.community ?? -1) || (b.degree || 0) - (a.degree || 0) || a.id - b.id)
    members.forEach((node, index) => {
      const angle = (index / members.length) * Math.PI * 2 - Math.PI / 2 + depth * 0.25
      positions.set(node.id, { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius })
    })
    rings.push({ r: radius, label: depth === orphanLevel && depth > reachedMax ? 'unconnected' : `${depth} step${depth > 1 ? 's' : ''}` })
  }

  return { mode: 'orbit', positions, clusters: [], lanes: [], rings, hubId: hub.id }
}

// ── 3. Domain columns ─────────────────────────────────────────────────────────
const LANE_ROWS = 22
const LANE_ROW_GAP = 30
const LANE_COL_GAP = 44
const LANE_GAP = 120

function layoutColumns(data: GraphData): LayoutResult {
  const byDomain = new Map<string, GraphNode[]>()
  for (const node of data.nodes) {
    const key = node.domain || 'other'
    if (!byDomain.has(key)) byDomain.set(key, [])
    byDomain.get(key)!.push(node)
  }
  const domains = orderDomains([...byDomain.keys()], d => byDomain.get(d)?.length || 0)

  const positions = new Map<number, Placed>()
  const lanes: LaneShape[] = []
  let cursorX = 0
  for (const domain of domains) {
    const members = byDomain.get(domain)!
      .slice()
      .sort((a, b) => (b.degree || 0) - (a.degree || 0) || a.title.localeCompare(b.title))
    const columns = Math.max(1, Math.ceil(members.length / LANE_ROWS))
    const rows = Math.ceil(members.length / columns)
    members.forEach((node, index) => {
      const column = Math.floor(index / rows)
      const row = index % rows
      positions.set(node.id, {
        x: cursorX + column * LANE_COL_GAP,
        y: row * LANE_ROW_GAP - ((rows - 1) * LANE_ROW_GAP) / 2,
      })
    })
    const width = (columns - 1) * LANE_COL_GAP
    const height = (rows - 1) * LANE_ROW_GAP
    lanes.push({
      key: domain,
      label: domain,
      count: members.length,
      color: domainColor(domain),
      x: cursorX - 30, y: -height / 2 - 34,
      w: width + 60, h: height + 68,
    })
    cursorX += width + LANE_GAP
  }

  const shift = recentre(positions)
  for (const lane of lanes) { lane.x += shift.x; lane.y += shift.y }
  return { mode: 'columns', positions, clusters: [], lanes, rings: [], hubId: null }
}

// ── shared ────────────────────────────────────────────────────────────────────
/** Slide everything so the drawing is centred on the origin — the canvas fits to 0,0. */
function recentre(positions: Map<number, Placed>): Placed {
  if (positions.size === 0) return { x: 0, y: 0 }
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
  for (const point of positions.values()) {
    if (point.x < minX) minX = point.x
    if (point.x > maxX) maxX = point.x
    if (point.y < minY) minY = point.y
    if (point.y > maxY) maxY = point.y
  }
  const shift = { x: -(minX + maxX) / 2, y: -(minY + maxY) / 2 }
  for (const point of positions.values()) { point.x += shift.x; point.y += shift.y }
  return shift
}

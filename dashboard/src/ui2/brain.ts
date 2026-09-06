// TOBI's memory graph, drawn from the real thing — ported line for line from the shell's
// script (docs/feature-idea-queue/TOBI_UI_2_SHELL.html). It thickens as he learns, and the
// circle is the one thing that never changes.
//
// One graph, one live wave. Each panel says what state it is in, and the state decides
// only how the connections behave; the nodes are identical everywhere.

/* How much of a brain there is. In the app these come from Brain V2's own graph,
   so the picture thickens as TOBI actually learns. Only the disc is fixed. */
const COUNT = 340   // memories and concepts
const COMMS = 6     // communities orbiting the core
const RIM = 0.26    // share sitting on the periphery, singly attached

/* One live wave, steered by the state machine. Amplitude and rate are eased rather
   than switched, and the phase is carried forward so changing the rate never jumps
   the front. dir -1 runs it inward, which is what listening looks like: sound
   arriving rather than an answer leaving. */
export const LIVE = { gain: 0, target: 0, phase: 0, rate: 1 / 2.6, dir: 1 as 1 | -1, last: 0 }
export function setWave(gain: number, period: number, dir: 1 | -1) {
  LIVE.target = gain; LIVE.rate = 1 / period; LIVE.dir = dir
}

type Node = { x: number; y: number; vx: number; vy: number; deg: number; g: number; rim: boolean; px: number; py: number; rad: number }
type Link = { a: number; b: number; bridge: boolean; r: number; w: number }
let nodes: Node[] = [], links: Link[] = []
let built = false

let seed = 20260827                     // seeded: the same brain on every load
function rnd() { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296 }

function build() {
  nodes = []; links = []
  const seen: Record<string, 1> = {}
  const link = (a: number, b: number, bridge: boolean) => {
    if (a === b) return
    const key = a < b ? a + '|' + b : b + '|' + a
    if (seen[key]) return
    seen[key] = 1
    links.push({ a, b, bridge, r: 0, w: 0 })
    nodes[a].deg++; nodes[b].deg++
  }

  /* communities: a dense core with satellites on a ring */
  const groups: { cx: number; cy: number; rad: number; share: number; ids: number[] }[] =
    [{ cx: 0, cy: 0, rad: 0.24, share: 0.26, ids: [] }]
  for (let c = 0; c < COMMS; c++) {
    const ang0 = (c / COMMS) * Math.PI * 2 - Math.PI / 2 + 0.22
    groups.push({ cx: Math.cos(ang0) * 0.52, cy: Math.sin(ang0) * 0.52, rad: 0.155 + rnd() * 0.03, share: (1 - 0.26) / COMMS, ids: [] })
  }

  const interior = Math.round(COUNT * (1 - RIM))
  for (let g = 0; g < groups.length; g++) {
    const G = groups[g], n = Math.round(interior * G.share)
    for (let i = 0; i < n; i++) {
      const th = rnd() * Math.PI * 2, rr = Math.sqrt(rnd()) * G.rad   // even area, not a pile
      nodes.push({ x: G.cx + Math.cos(th) * rr, y: G.cy + Math.sin(th) * rr, vx: 0, vy: 0, deg: 0, g, rim: false, px: 0, py: 0, rad: 0 })
      G.ids.push(nodes.length - 1)
    }
  }

  /* periphery: an even ring, lightly jittered, one link inward */
  const rimCount = COUNT - nodes.length, rimIds: number[] = []
  for (let k = 0; k < rimCount; k++) {
    const a2 = (k / rimCount) * Math.PI * 2 + (rnd() - 0.5) * 0.055
    const r3 = 0.9 + rnd() * 0.075
    nodes.push({ x: Math.cos(a2) * r3, y: Math.sin(a2) * r3, vx: 0, vy: 0, deg: 0, g: -1, rim: true, px: 0, py: 0, rad: 0 })
    rimIds.push(nodes.length - 1)
  }

  /* inside a community, join each node to its two nearest neighbours */
  for (const G of groups) {
    const ids = G.ids
    for (let u = 0; u < ids.length; u++) {
      const A = nodes[ids[u]], best: number[] = [], bd: number[] = []
      for (let v = 0; v < ids.length; v++) {
        if (v === u) continue
        const B = nodes[ids[v]], dd0 = (B.x - A.x) * (B.x - A.x) + (B.y - A.y) * (B.y - A.y)
        if (best.length < 2) { best.push(ids[v]); bd.push(dd0) }
        else {
          const worst = bd[0] > bd[1] ? 0 : 1
          if (dd0 < bd[worst]) { best[worst] = ids[v]; bd[worst] = dd0 }
        }
      }
      for (const w0 of best) link(ids[u], w0, false)
    }
  }

  /* a few clean bridges: core to each satellite, and neighbour to neighbour */
  function bridge(g1: number, g2: number, howMany: number) {
    const A2 = groups[g1].ids, B2 = groups[g2].ids, pairs: [number, number, number][] = []
    for (const a of A2) for (const b of B2) {
      const p1 = nodes[a], p2 = nodes[b]
      pairs.push([(p2.x - p1.x) * (p2.x - p1.x) + (p2.y - p1.y) * (p2.y - p1.y), a, b])
    }
    pairs.sort((m, n2) => m[0] - n2[0])
    const used: Record<number, 1> = {}
    for (let z = 0, made = 0; z < pairs.length && made < howMany; z++) {
      if (used[pairs[z][1]] || used[pairs[z][2]]) continue
      used[pairs[z][1]] = used[pairs[z][2]] = 1
      link(pairs[z][1], pairs[z][2], true); made++
    }
  }
  for (let b2 = 1; b2 < groups.length; b2++) {
    bridge(0, b2, 3)
    bridge(b2, b2 === groups.length - 1 ? 1 : b2 + 1, 2)
  }

  /* every rim node hangs off the nearest interior node */
  for (const Ri of rimIds) {
    const Rn = nodes[Ri]
    let pick = -1, pd = 1e9
    for (let t2 = 0; t2 < nodes.length; t2++) {
      if (nodes[t2].rim) continue
      const dx2 = nodes[t2].x - Rn.x, dy2 = nodes[t2].y - Rn.y, d2 = dx2 * dx2 + dy2 * dy2
      if (d2 < pd) { pd = d2; pick = t2 }
    }
    if (pick >= 0) link(Ri, pick, false)
  }
}

/* springs pull, neighbours push, communities hold together, the disc is the wall */
function relax(passes: number) {
  const cent: { x: number; y: number; n: number }[] = []
  for (const n of nodes) {
    if (n.g < 0) continue
    if (!cent[n.g]) cent[n.g] = { x: 0, y: 0, n: 0 }
    cent[n.g].x += n.x; cent[n.g].y += n.y; cent[n.g].n++
  }
  for (const c of cent) if (c) { c.x /= c.n; c.y /= c.n }

  for (let it = 0; it < passes; it++) {
    const alpha = 1 - it / passes
    for (const L of links) {
      const A = nodes[L.a], B = nodes[L.b]
      const dx = B.x - A.x, dy = B.y - A.y, d = Math.hypot(dx, dy) || 1e-4
      const want = L.bridge ? 0.2 : 0.062
      const fr = (d - want) * 0.05 * alpha
      A.vx += dx / d * fr; A.vy += dy / d * fr; B.vx -= dx / d * fr; B.vy -= dy / d * fr
    }
    for (let i2 = 0; i2 < nodes.length; i2++) {
      for (let j2 = i2 + 1; j2 < nodes.length; j2++) {
        const a3 = nodes[i2], b3 = nodes[j2]
        const ax = b3.x - a3.x, ay = b3.y - a3.y, dd = ax * ax + ay * ay
        if (dd > 0.0075 || dd === 0) continue      // short range only — keeps dots off each other
        const m2 = (0.00016 / (dd + 0.0002)) * alpha
        a3.vx -= ax * m2; a3.vy -= ay * m2; b3.vx += ax * m2; b3.vy += ay * m2
      }
    }
    for (const n3 of nodes) {
      if (n3.g >= 0 && cent[n3.g]) {
        n3.vx += (cent[n3.g].x - n3.x) * 0.010 * alpha
        n3.vy += (cent[n3.g].y - n3.y) * 0.010 * alpha
      }
      n3.x += n3.vx; n3.y += n3.vy; n3.vx *= 0.6; n3.vy *= 0.6
      const rr2 = Math.hypot(n3.x, n3.y), cap = n3.rim ? 0.985 : 0.84
      if (rr2 > cap) { n3.x = n3.x / rr2 * cap; n3.y = n3.y / rr2 * cap }
    }
  }

  for (const n of nodes) {
    n.px = n.x; n.py = n.y
    n.rad = Math.hypot(n.px, n.py)   // when the boot sweep reaches it
  }
  for (const L of links) {           // when the front reaches it, plus a little of its own
    const P = nodes[L.a], Q = nodes[L.b]
    L.r = Math.hypot((P.px + Q.px) / 2, (P.py + Q.py) / 2) + (rnd() - 0.5) * 0.15
  }
}

export function ensureBuilt() { if (!built) { build(); relax(120); built = true } }

/** Advance the wave. `t` is seconds; a still (reduced-motion) caller passes a constant. */
export function advance(t: number) {
  const dt = LIVE.last ? Math.max(0, Math.min(0.05, t - LIVE.last)) : 0   // never run the wave backwards
  LIVE.last = t
  LIVE.gain += (LIVE.target - LIVE.gain) * Math.min(1, dt * 4.2)   // settles in about 420ms
  LIVE.phase = (LIVE.phase + dt * LIVE.rate) % 1
}

export type BrainState = 'asleep' | 'booting' | 'live'
export type Panel = { ctx: CanvasRenderingContext2D; W: number; H: number; CX: number; CY: number; R: number }

export function paint(p: Panel, state: BrainState, t: number, still: boolean, bootStart: number) {
  const ctx = p.ctx, R = p.R, CX = p.CX, CY = p.CY
  ctx.clearRect(0, 0, p.W, p.H)

  /* asleep: the graph is there, nothing is moving through it */
  if (state === 'asleep') {
    ctx.lineCap = 'butt'; ctx.lineWidth = 0.55
    ctx.strokeStyle = 'rgba(139,148,158,.075)'
    ctx.beginPath()
    for (const L of links) {
      const A0 = nodes[L.a], B0 = nodes[L.b]
      ctx.moveTo(CX + A0.px * R, CY + A0.py * R); ctx.lineTo(CX + B0.px * R, CY + B0.py * R)
    }
    ctx.stroke()
    for (const m0 of nodes) {
      const d0 = Math.min(m0.deg, 7)
      ctx.beginPath()
      ctx.arc(CX + m0.px * R, CY + m0.py * R, m0.rim ? 0.7 : 0.9 + d0 * 0.1, 0, 6.2832)
      ctx.fillStyle = 'rgba(139,148,158,' + (m0.rim ? 0.2 : 0.26 + d0 * 0.028).toFixed(3) + ')'
      ctx.fill()
    }
    return
  }

  /* booting: the graph assembles outward, once per cycle, and holds what it has built */
  if (state === 'booting') {
    const BUILD = 3.5                       // the assembly finishes just before the shell hands over
    const reveal = still ? 1 : (bootStart > 0 ? Math.min(1, (t - bootStart) / BUILD) : 0)
    ctx.lineCap = 'butt'; ctx.lineWidth = 0.6
    for (let tier0 = 0; tier0 < 2; tier0++) {
      ctx.strokeStyle = tier0 ? 'rgba(158,206,255,.22)' : 'rgba(88,166,255,.075)'
      ctx.beginPath()
      for (const L1 of links) {
        if (L1.r > reveal) continue
        const fresh = L1.r > reveal - 0.11
        if ((tier0 === 1) !== fresh) continue
        const A1 = nodes[L1.a], B1 = nodes[L1.b]
        ctx.moveTo(CX + A1.px * R, CY + A1.py * R); ctx.lineTo(CX + B1.px * R, CY + B1.py * R)
      }
      ctx.stroke()
    }
    for (const m1 of nodes) {
      if (m1.rad > reveal) continue
      const d1 = Math.min(m1.deg, 7)
      const young = Math.max(0, 1 - (reveal - m1.rad) / 0.11)
      ctx.beginPath()
      ctx.arc(CX + m1.px * R, CY + m1.py * R, (m1.rim ? 0.75 : 1 + d1 * 0.13) + young * 0.9, 0, 6.2832)
      ctx.fillStyle = 'rgba(' + Math.round(158 + 60 * young) + ',' + Math.round(206 + 34 * young) + ',255,' +
                      Math.min(0.95, (m1.rim ? 0.3 : 0.4 + d1 * 0.05) + young * 0.45).toFixed(3) + ')'
      ctx.fill()
    }
    return
  }

  /* live: one front crosses the graph, and how it crosses is the state */
  const base = 0.042 + LIVE.gain * 0.045
  const gain = 0.17 + LIVE.gain * 0.4
  const SIG = 0.075, REACH = 1.12

  const phase = LIVE.phase
  const front = LIVE.dir > 0 ? phase * REACH : REACH - phase * REACH
  const rise = Math.min(1, phase / 0.12)
  const fall = Math.max(0, 1 - Math.max(0, (phase - 0.82) / 0.18))
  const amp = rise * rise * (3 - 2 * rise) * (fall * fall * (3 - 2 * fall)) * LIVE.gain

  for (const L of links) {
    let w = 0
    if (amp > 0) {
      const dd = L.r - front
      w = Math.exp(-(dd * dd) / (2 * SIG * SIG)) * amp
    }
    L.w = w
  }

  const TIERS = 14, tier: number[][] = []
  for (let i = 0; i < TIERS; i++) tier.push([])
  for (let e = 0; e < links.length; e++) {
    const v = links[e].w + (links[e].bridge ? 0.1 : 0)
    const idx = (v * (TIERS - 1)) | 0
    tier[idx > TIERS - 1 ? TIERS - 1 : idx].push(e)
  }
  ctx.lineCap = 'butt'
  for (let i = 0; i < TIERS; i++) {
    if (!tier[i].length) continue
    const f2 = i / (TIERS - 1)
    const soft = Math.pow(f2, 1.35)
    ctx.lineWidth = 0.6 + soft * 0.4
    ctx.strokeStyle = 'rgba(' + Math.round(88 + 118 * soft) + ',' +
                      Math.round(166 + 68 * soft) + ',255,' + (base + gain * soft).toFixed(3) + ')'
    ctx.beginPath()
    for (const e of tier[i]) {
      const L2 = links[e], P2 = nodes[L2.a], Q2 = nodes[L2.b]
      ctx.moveTo(CX + P2.px * R, CY + P2.py * R)
      ctx.lineTo(CX + Q2.px * R, CY + Q2.py * R)
    }
    ctx.stroke()
  }

  for (const m3 of nodes) {
    const deg = Math.min(m3.deg, 7)
    const na = m3.rim ? 0.32 : 0.42 + deg * 0.055
    ctx.beginPath()
    ctx.arc(CX + m3.px * R, CY + m3.py * R, m3.rim ? 0.75 : 1 + deg * 0.13, 0, 6.2832)
    ctx.fillStyle = 'rgba(158,206,255,' + Math.min(na, 0.92).toFixed(3) + ')'
    ctx.fill()
  }
}

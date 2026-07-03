/**
 * Dependency-free SVG charts for the premium chat (Premium Chat v2 · P2).
 * Rendered from a ```tobi:chart``` JSON block. Three families: bar, line, donut.
 * Theme-aware (accent / purple / success / warning / danger tokens), responsive
 * (viewBox + width 100%), and calm under reduced-motion (no entrance animation).
 *
 * Shape:
 *   { "type": "bar" | "line" | "donut", "title"?: string,
 *     "series": [{ "label": string, "value": number, "color"?: token }] }
 *   line also accepts { "points": number[] } or series of values.
 */

const TOKENS = ['accent', 'purple', 'success', 'warning', 'danger'] as const
const colorAt = (i: number, c?: string) =>
  `rgb(var(--${c && (TOKENS as readonly string[]).includes(c) ? c : TOKENS[i % TOKENS.length]}))`

type Pt = { label: string; value: number; color?: string }

function normalize(data: any): Pt[] {
  if (Array.isArray(data.series)) {
    return data.series.map((s: any, i: number) =>
      typeof s === 'number'
        ? { label: String(i + 1), value: s }
        : { label: String(s.label ?? s.name ?? i + 1), value: Number(s.value ?? s.y ?? 0), color: s.color })
  }
  if (Array.isArray(data.points)) return data.points.map((v: number, i: number) => ({ label: String(i + 1), value: Number(v) }))
  if (Array.isArray(data.data)) return data.data.map((s: any, i: number) => ({ label: String(s.label ?? i + 1), value: Number(s.value ?? 0), color: s.color }))
  return []
}

function Frame({ title, children }: { title?: string; children: React.ReactNode }) {
  return (
    <div className="my-2 rounded-xl border border-border bg-surface/50 p-3.5">
      {title && <div className="mb-2 text-sm font-semibold text-heading">{title}</div>}
      {children}
    </div>
  )
}

function BarChart({ pts, title }: { pts: Pt[]; title?: string }) {
  const max = Math.max(1, ...pts.map(p => Math.abs(p.value)))
  const W = 320, H = 150, pad = 6, n = pts.length || 1
  const bw = (W - pad * 2) / n
  return (
    <Frame title={title}>
      <svg viewBox={`0 0 ${W} ${H + 22}`} className="w-full" preserveAspectRatio="xMidYMid meet">
        {[0.25, 0.5, 0.75].map(g => <line key={g} x1={pad} x2={W - pad} y1={H * g} y2={H * g} stroke="rgb(var(--border))" strokeWidth={0.5} />)}
        {pts.map((p, i) => {
          const h = (Math.abs(p.value) / max) * (H - 10)
          const x = pad + i * bw
          return (
            <g key={i}>
              <rect x={x + bw * 0.18} y={H - h} width={bw * 0.64} height={h} rx={3} fill={colorAt(i, p.color)} className="chart-rise" style={{ transformOrigin: `center ${H}px` }} />
              <text x={x + bw / 2} y={H + 13} textAnchor="middle" className="fill-muted" style={{ fontSize: 9 }}>{p.label.slice(0, 8)}</text>
              <text x={x + bw / 2} y={H - h - 3} textAnchor="middle" className="fill-heading" style={{ fontSize: 9, fontWeight: 600 }}>{p.value}</text>
            </g>
          )
        })}
      </svg>
    </Frame>
  )
}

function LineChart({ pts, title }: { pts: Pt[]; title?: string }) {
  const W = 320, H = 150, pad = 8
  const max = Math.max(1, ...pts.map(p => p.value)), min = Math.min(0, ...pts.map(p => p.value))
  const span = max - min || 1, n = pts.length
  const x = (i: number) => pad + (i / Math.max(1, n - 1)) * (W - pad * 2)
  const y = (v: number) => H - 8 - ((v - min) / span) * (H - 18)
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(p.value).toFixed(1)}`).join(' ')
  const area = `${line} L${x(n - 1).toFixed(1)} ${H} L${x(0).toFixed(1)} ${H} Z`
  return (
    <Frame title={title}>
      <svg viewBox={`0 0 ${W} ${H + 22}`} className="w-full" preserveAspectRatio="xMidYMid meet">
        {[0.25, 0.5, 0.75].map(g => <line key={g} x1={pad} x2={W - pad} y1={H * g} y2={H * g} stroke="rgb(var(--border))" strokeWidth={0.5} />)}
        <defs><linearGradient id="lc-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgb(var(--accent))" stopOpacity={0.28} /><stop offset="100%" stopColor="rgb(var(--accent))" stopOpacity={0} />
        </linearGradient></defs>
        <path d={area} fill="url(#lc-fill)" />
        <path d={line} fill="none" stroke="rgb(var(--accent))" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" className="chart-draw" />
        {pts.map((p, i) => <circle key={i} cx={x(i)} cy={y(p.value)} r={2.6} fill="rgb(var(--accent))" />)}
        {pts.map((p, i) => (i % Math.ceil(n / 6 || 1) === 0 || i === n - 1) &&
          <text key={`t${i}`} x={x(i)} y={H + 13} textAnchor="middle" className="fill-muted" style={{ fontSize: 9 }}>{p.label.slice(0, 8)}</text>)}
      </svg>
    </Frame>
  )
}

function DonutChart({ pts, title }: { pts: Pt[]; title?: string }) {
  const total = pts.reduce((a, p) => a + Math.abs(p.value), 0) || 1
  const R = 52, r = 32, cx = 70, cy = 70
  let acc = 0
  const arcs = pts.map((p, i) => {
    const frac = Math.abs(p.value) / total
    const a0 = acc * 2 * Math.PI - Math.PI / 2
    acc += frac
    const a1 = acc * 2 * Math.PI - Math.PI / 2
    const large = frac > 0.5 ? 1 : 0
    const pt = (rad: number, ang: number) => [cx + rad * Math.cos(ang), cy + rad * Math.sin(ang)]
    const [x0, y0] = pt(R, a0), [x1, y1] = pt(R, a1), [x2, y2] = pt(r, a1), [x3, y3] = pt(r, a0)
    const d = `M${x0} ${y0} A${R} ${R} 0 ${large} 1 ${x1} ${y1} L${x2} ${y2} A${r} ${r} 0 ${large} 0 ${x3} ${y3} Z`
    return { d, color: colorAt(i, p.color), p, frac }
  })
  return (
    <Frame title={title}>
      <div className="flex flex-wrap items-center gap-4">
        <svg viewBox="0 0 140 140" className="h-32 w-32 shrink-0">
          {arcs.map((a, i) => <path key={i} d={a.d} fill={a.color} className="chart-fade" />)}
          <text x={cx} y={cy - 2} textAnchor="middle" className="fill-heading" style={{ fontSize: 15, fontWeight: 700 }}>{total}</text>
          <text x={cx} y={cy + 12} textAnchor="middle" className="fill-muted" style={{ fontSize: 8, textTransform: 'uppercase' }}>total</text>
        </svg>
        <div className="space-y-1.5">
          {arcs.map((a, i) => (
            <div key={i} className="flex items-center gap-2 text-xs">
              <span className="h-2.5 w-2.5 rounded-sm" style={{ background: a.color }} />
              <span className="text-text">{a.p.label}</span>
              <span className="text-muted">{a.p.value} · {Math.round(a.frac * 100)}%</span>
            </div>
          ))}
        </div>
      </div>
    </Frame>
  )
}

export default function Chart({ raw }: { raw: string }) {
  let data: any
  try { data = JSON.parse(raw) } catch { return <pre className="my-2 overflow-x-auto rounded-lg border border-border bg-bg/60 px-3 py-2 text-xs text-muted">{raw}</pre> }
  const pts = normalize(data)
  if (!pts.length) return null
  const type = String(data.type || 'bar').toLowerCase()
  if (type === 'line' || type === 'area') return <LineChart pts={pts} title={data.title} />
  if (type === 'donut' || type === 'pie' || type === 'doughnut') return <DonutChart pts={pts} title={data.title} />
  return <BarChart pts={pts} title={data.title} />
}

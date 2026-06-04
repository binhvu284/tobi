import { motion } from 'framer-motion'

type Series = {
  label: string
  color: string
  /** One value (0–100) per axis, in axis order. */
  values: number[]
}

type Props = {
  axes: string[]
  series: Series[]
  /** Square SVG size in px. */
  size?: number
  className?: string
}

/**
 * A dependency-free SVG radar/spider chart. Renders grid rings + one spoke per
 * axis + an animated translucent polygon per series (overlay 2–3). Values 0–100.
 */
export default function RadarChart({ axes, series, size = 320, className = '' }: Props) {
  const n = axes.length
  const cx = size / 2
  const cy = size / 2
  const maxR = size / 2 - 38 // leave room for labels
  const rings = [0.25, 0.5, 0.75, 1]

  // Axis i points straight up (-90°) then clockwise.
  const angle = (i: number) => -Math.PI / 2 + (i * 2 * Math.PI) / n
  const point = (i: number, r: number): [number, number] => [
    cx + Math.cos(angle(i)) * r,
    cy + Math.sin(angle(i)) * r,
  ]
  const polygon = (values: number[], scale = 1) =>
    values
      .map((v, i) => point(i, (Math.max(0, Math.min(100, v)) / 100) * maxR * scale).join(','))
      .join(' ')

  return (
    <div className={`flex flex-col items-center gap-3 ${className}`}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ overflow: 'visible' }}>
        {/* grid rings */}
        {rings.map((rr) => (
          <polygon
            key={rr}
            points={Array.from({ length: n }, (_, i) => point(i, maxR * rr).join(',')).join(' ')}
            fill="none"
            stroke="#30363d"
            strokeWidth={1}
          />
        ))}

        {/* spokes + axis labels */}
        {axes.map((ax, i) => {
          const [ex, ey] = point(i, maxR)
          const [lx, ly] = point(i, maxR + 20)
          return (
            <g key={ax}>
              <line x1={cx} y1={cy} x2={ex} y2={ey} stroke="#30363d" strokeWidth={1} />
              <text
                x={lx}
                y={ly}
                fill="#8b949e"
                fontSize={11}
                textAnchor={Math.abs(lx - cx) < 4 ? 'middle' : lx > cx ? 'start' : 'end'}
                dominantBaseline="middle"
                className="font-mono uppercase"
              >
                {ax}
              </text>
            </g>
          )
        })}

        {/* one animated polygon per series */}
        {series.map((s) => (
          <motion.g
            key={s.label}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5, ease: 'easeOut' }}
            style={{ transformOrigin: `${cx}px ${cy}px` }}
          >
            <motion.polygon
              points={polygon(s.values)}
              fill={s.color}
              fillOpacity={0.18}
              stroke={s.color}
              strokeWidth={2}
              initial={{ scale: 0.2, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ duration: 0.7, ease: 'easeOut' }}
              style={{ transformOrigin: `${cx}px ${cy}px` }}
            />
            {s.values.map((v, i) => {
              const [px, py] = point(i, (Math.max(0, Math.min(100, v)) / 100) * maxR)
              return <circle key={i} cx={px} cy={py} r={3} fill={s.color} />
            })}
          </motion.g>
        ))}
      </svg>

      {/* legend */}
      <div className="flex flex-wrap justify-center gap-3">
        {series.map((s) => (
          <span key={s.label} className="flex items-center gap-1.5 text-xs text-text">
            <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  )
}
